"""OS_V1 Permissions — the gate that makes device-level control safe.

Clean-room ruleset engine modeled on the layered permission systems studied
in sst/opencode (permission.ts: rules {action, resource, effect}, last
matching rule wins, default "ask", persisted per-project grants) and sized
for the OpenClaw-style device control being merged into OSS Work next.

Design:
- A RULE = {action, resource, effect} where resource is a glob pattern
  ("cmd:*git*", "path:C:/Users/ce/Documents/**", "tool:exec").
- Matching: the LAST matching rule wins (so deny at the end can override a
  broad earlier allow). No match ⇒ "ask" (safe default).
- Decisions: allow / ask / deny. "ask" blocks the tool call until a human
  answers through the UI (SSE permission event → modal → reply).
- Persistent grants: a user "always allow" answer is stored as a saved rule
  (JSON, human-readable, auditable) so the same operation never re-asks.
- Yolo mode: explicitly skips ask (never deny) — for the user's own machine
  with full trust. It is a configured choice, never a silent default.
- Audit: every decision is appended to an in-memory ring + JSONL file.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import time
from pathlib import Path

ALLOW, ASK, DENY = "allow", "ask", "deny"


def _data_dir() -> Path:
    base = os.environ.get("OSV_DATA_DIR") or os.path.join(
        os.environ.get("TEMP", "."), "osv_data")
    d = Path(base) / "permissions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rules_file() -> Path:
    return _data_dir() / "saved_rules.json"


def _audit_file() -> Path:
    return _data_dir() / "audit.jsonl"


# ---------------------------------------------------------------------------
# Glob matching — supports ** for path patterns, * within segments
# ---------------------------------------------------------------------------

def _match(pattern: str, resource: str) -> bool:
    """Glob match. '**' spans path separators; '*' does not."""
    p = (pattern or "").strip()
    r = (resource or "").strip()
    if p == "*" or p.lower() == r.lower():
        return True
    # path-style: normalize separators, then ** aware match
    pn = p.replace("\\", "/")
    rn = r.replace("\\", "/")
    if "**" in pn:
        rx = re.escape(pn).replace(re.escape("**"), "\0").replace(
            re.escape("*"), "[^/]*").replace("\0", ".*")
        return re.fullmatch(rx, rn, re.IGNORECASE) is not None
    if "*" in pn or "?" in pn:
        return fnmatch.fnmatch(rn.lower(), pn.lower())
    return pn.lower() == rn.lower()


class PermissionEngine:
    """Stateful gate: config rules + saved grants + yolo + audit."""

    def __init__(self, yolo: bool = False, rules: list[dict] | None = None,
                 data_dir: Path | None = None):
        self.yolo = bool(yolo)
        self.rules: list[dict] = list(rules or [])   # session rules (highest layer)
        self._dd = data_dir  # test seam; None → _data_dir()  (BEFORE load!)
        self.saved: list[dict] = self._load_saved()
        self.audit: list[dict] = []

    # -- persistence -------------------------------------------------------
    def _rules_path(self) -> Path:
        return (self._dd / "saved_rules.json") if self._dd else _rules_file()

    def _audit_path(self) -> Path:
        return (self._dd / "audit.jsonl") if self._dd else _audit_file()

    def _load_saved(self) -> list[dict]:
        try:
            return json.loads(self._rules_path().read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — missing/corrupt file = empty grants
            return []

    def save_grant(self, action: str, resource: str) -> None:
        """User said 'always allow' — persist so we never re-ask."""
        self.saved.append({"action": action, "resource": resource,
                           "effect": ALLOW, "ts": time.time()})
        try:
            self._rules_path().write_text(
                json.dumps(self.saved, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception:  # noqa: BLE001, S110 — persistence failure must not crash
            pass

    def forget_grants(self) -> int:
        n = len(self.saved)
        self.saved = []
        try:
            self._rules_path().write_text("[]", encoding="utf-8")
        except Exception:  # noqa: BLE001, S110
            pass
        return n

    # -- the decision ------------------------------------------------------
    @staticmethod
    def _specificity(pattern: str) -> int:
        """Literal (non-wildcard) characters — the more, the more specific."""
        return len(re.sub(r"[*?]", "", pattern or ""))

    def evaluate(self, action: str, resource: str = "*") -> str:
        """→ 'allow' | 'ask' | 'deny'.

        Semantics (the ones a device policy actually needs):
        1. Any matching DENY ⇒ deny (absolute — an 'always allow' can never
           resurrect a denied lane).
        2. Otherwise the MOST SPECIFIC matching rule wins (literal chars);
           ties break to the later rule (saved grants load before session
           rules, so an explicit session override beats an old grant).
        3. No match ⇒ ask (safe default). Yolo never asks."""
        if self.yolo:
            self._log(action, resource, ALLOW, "yolo")
            return ALLOW
        matches = []
        for idx, rule in enumerate(self.saved + self.rules):
            if rule.get("action") not in (None, action):
                continue
            if _match(rule.get("resource", "*"), resource):
                matches.append((idx, rule))
        if not matches:
            decision = ASK
        elif any(r.get("effect") == DENY for _i, r in matches):
            decision = DENY
        else:
            best = max(matches, key=lambda t: (self._specificity(t[1].get("resource", "*")), t[0]))
            decision = best[1].get("effect", ASK)
        self._log(action, resource, decision, "ruleset")
        return decision

    def add_rule(self, action: str, resource: str, effect: str) -> None:
        """Session-level rule (config/plugins). Overrides saved grants because
        it is evaluated after them (last match wins)."""
        self.rules.append({"action": action, "resource": resource,
                           "effect": effect, "ts": time.time()})

    # -- audit -------------------------------------------------------------
    def _log(self, action: str, resource: str, decision: str, layer: str) -> None:
        entry = {"ts": round(time.time(), 3), "action": action,
                 "resource": resource[:200], "decision": decision, "layer": layer}
        self.audit.append(entry)
        if len(self.audit) > 500:
            self.audit = self.audit[-300:]
        try:
            with self._audit_path().open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001, S110 — audit file must never break serving
            pass


# ---------------------------------------------------------------------------
# The blocking gate used by tools: evaluate → maybe ask the human → verdict
# ---------------------------------------------------------------------------

class AskDenied(Exception):
    """The user (or policy) refused this operation."""


class PermissionGate:
    """Wires the engine to a UI ask-channel. ask_fn(action, resource, what)
    must return 'allow' | 'always' | 'deny' (or raise/disconnect ⇒ deny)."""

    def __init__(self, engine: PermissionEngine, ask_fn=None):
        self.engine = engine
        self.ask_fn = ask_fn

    def check(self, action: str, resource: str = "*", what: str = "") -> bool:
        d = self.engine.evaluate(action, resource)
        if d == ALLOW:
            return True
        if d == DENY:
            raise AskDenied(f"العملية مرفوضة بسياسة صلاحيات OSS: {action} {resource}")
        # ask the human
        if self.ask_fn is None:
            raise AskDenied(f"العملية تحتاج موافقتك وواجهة الموافقة غير متاحة: {what}")
        try:
            answer = self.ask_fn(action, resource, what)
        except AskDenied:
            raise
        except Exception as exc:  # — a broken ask channel = deny
            raise AskDenied(f"تعذّر سؤالك عن الموافقة ({str(exc)[:60]}) — رُفضت العملية") from exc
        if answer == "always":
            self.engine.save_grant(action, resource)
            return True
        if answer == "allow":
            return True
        raise AskDenied(f"رفضتَ العملية: {what}")


def default_rules_for_device_control() -> list[dict]:
    """The OSS policy baseline for device tools (session rules layer).
    Safe-by-default with the useful lanes open — the OPENCLAW merge will
    extend this list with its exec classification."""
    return [
        # always-on lanes
        {"action": "device.info",   "resource": "*", "effect": ALLOW},
        {"action": "device.notify", "resource": "*", "effect": ALLOW},
        # files: home/Documents allowed, system secrets never
        {"action": "device.file.read", "resource": "path:C:/Users/**", "effect": ALLOW},
        {"action": "device.file.read", "resource": "path:**/AppData/**", "effect": ASK},
        {"action": "device.file.write", "resource": "path:C:/Users/ce/Documents/**", "effect": ALLOW},
        {"action": "device.file.write", "resource": "path:**", "effect": ASK},
        # processes: listing free, killing needs approval
        {"action": "device.process.list", "resource": "*", "effect": ALLOW},
        {"action": "device.process.kill", "resource": "*", "effect": ASK},
        # exec: read-only probes free; everything else ask
        {"action": "device.exec", "resource": "cmd:get*", "effect": ALLOW},
        {"action": "device.exec", "resource": "cmd:*--version*", "effect": ALLOW},
        {"action": "device.exec", "resource": "cmd:*", "effect": ASK},
        # hard denials that no "always allow" can override (checked last)
        {"action": "device.exec", "resource": "cmd:*format*msys*", "effect": DENY},
        {"action": "device.exec", "resource": "cmd:*rd /s *", "effect": DENY},
        {"action": "device.exec", "resource": "cmd:*diskpart*", "effect": DENY},
        {"action": "device.exec", "resource": "cmd:*vssadmin*delete*", "effect": DENY},
        {"action": "device.exec", "resource": "cmd:*bcdedit*", "effect": DENY},
        {"action": "device.file.write", "resource": "path:C:/Windows/**", "effect": DENY},
    ]
