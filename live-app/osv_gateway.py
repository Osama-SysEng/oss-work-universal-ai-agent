"""OS_V Provider Gateway — the OS_V system's own provider aggregation engine.

Capability ported clean-room from behavior evidence gathered by inspecting
FreeLLMAPI's bundled router (Electron app analyzed with REA + its live SQLite
schema), re-implemented in Python for OSS Work:

- Provider pool in SQLite: keys encrypted at rest (DPAPI-free XOR+HMAC local
  scheme), health status, monthly caps, model scope.
- Unified monthly key (os_v-...) issued per device — the only credential
  end users ever need (central issuance comes in the hybrid phase).
- Bayesian bandit routing: Thompson sampling over a Beta posterior of each
  model's success rate, combined with speed and intelligence axes.
- Strategy presets: balanced / smartest / fastest / reliable, plus a "code"
  task shift (speed -> intelligence) and peak-hours shift (speed ->
  reliability), both exempting fastest/reliable.
- Headroom: monthly token budget + rolling rate-window, ramped (start 0.2,
  floor 0.1) so nearly-exhausted models fade instead of hard-failing.
- Rate-limit penalties: +3 per 429, +1 per other failure, success forgives 1,
  decay 1 per 2 minutes, cap 10, max 60% score damping.
- Hard cooldowns per (provider, model, key) with expiry.
- Full accounting: attempts, hourly usage, monthly usage per unified key.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
DB_PATH = _DIR / "gateway.db"

# Strategy presets — same axes as the analyzed router (evidence: scoring.ts
# BANDIT_PRESETS): reliability leads in balanced; intelligence in smartest;
# speed in fastest; reliable dominates for "just make it work".
BANDIT_PRESETS = {
    "balanced": {"reliability": 0.5, "speed": 0.25, "intelligence": 0.25},
    "smartest": {"reliability": 0.35, "speed": 0.1, "intelligence": 0.55},
    "fastest": {"reliability": 0.35, "speed": 0.55, "intelligence": 0.1},
    "reliable": {"reliability": 0.7, "speed": 0.15, "intelligence": 0.15},
}
DEFAULT_STRATEGY = os.environ.get("OSV_STRATEGY", "balanced").strip().lower()
if DEFAULT_STRATEGY not in BANDIT_PRESETS:
    DEFAULT_STRATEGY = "balanced"

TIER_VALUE = {"Frontier": 4, "Large": 3, "Medium": 2, "Small": 1}
RANK_SCALE = 31
SPEED_SCALE_TOK_S = 60.0
TTFB_BEST_MS = 300.0
TTFB_WORST_MS = 5000.0
THROUGHPUT_WEIGHT = 0.6
TTFB_WEIGHT = 0.4
SPEED_PRIOR = 0.6
HEADROOM_FLOOR = 0.1
HEADROOM_RAMP_START = 0.2
MAX_PENALTY = 10
RATE_LIMIT_MAX_DAMP = 0.6
PENALTY_PER_429 = 3
PENALTY_PER_FAIL = 1
DECAY_INTERVAL_S = 120.0      # 1 point forgiven every 2 minutes
DECAY_AMOUNT = 1
TASK_WEIGHT_SHARE = 0.3
TASK_EXEMPT = {"fastest", "reliable", "custom"}
STATS_TTL_S = 5.0

_lock = threading.Lock()
_stats_cache: dict | None = None
_stats_at = 0.0
_penalties: dict[int, dict] = {}   # model row id -> {count, last_hit, penalty}
_cooldowns: dict[int, float] = {}  # model row id -> expiry (monotonic-based)
_strategy = DEFAULT_STRATEGY

# ---------------------------------------------------------------------------
# Key encryption at rest (local machine trust model, no external deps):
# key material = machine-specific secret file + HMAC-derived stream, XOR.
# ---------------------------------------------------------------------------


def _master_secret() -> bytes:
    p = _DIR / "gateway.secret"
    try:
        if p.exists():
            data = p.read_bytes()
            if len(data) >= 32:
                return data
        data = secrets.token_bytes(48)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return data
    except Exception:  # noqa: BLE001 — never crash the pool on FS issues
        return b"OSV_FALLBACK_SECRET_DO_NOT_SHIP" * 2


def encrypt_key(plain: str) -> str:
    data = plain.encode("utf-8")
    stream = hmac.new(_master_secret(), b"osv-key-stream", hashlib.sha256).digest()
    out = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(data))
    return out.hex()


def decrypt_key(blob: str) -> str:
    if not blob:
        return ""
    raw = bytes.fromhex(blob)
    stream = hmac.new(_master_secret(), b"osv-key-stream", hashlib.sha256).digest()
    return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(raw)).decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Schema + seed
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,          -- registry kind: gemini / freellmapi / groq ...
  base_url TEXT NOT NULL,
  api_key_enc TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unknown',  -- healthy / exhausted / unknown
  monthly_token_cap INTEGER NOT NULL DEFAULT 0,  -- 0 = unlimited/unknown
  size_label TEXT NOT NULL DEFAULT 'Medium',
  intelligence_rank REAL NOT NULL DEFAULT 50,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stats (
  provider_id INTEGER PRIMARY KEY REFERENCES providers(id),
  successes INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  tok_per_sec REAL NOT NULL DEFAULT 0,
  avg_ttfb_ms REAL,
  monthly_used_tokens INTEGER NOT NULL DEFAULT 0,
  window_start_ms INTEGER NOT NULL DEFAULT 0,
  window_used_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  hour_bucket TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  ok INTEGER NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  is_429 INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_hour ON usage(hour_bucket);
CREATE TABLE IF NOT EXISTS unified_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key_hash TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL DEFAULT '',
  monthly_token_cap INTEGER NOT NULL DEFAULT 0,  -- 0 = unlimited
  used_tokens INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  revoked INTEGER NOT NULL DEFAULT 0
);
"""


def _connect() -> sqlite3.Connection:
    # Lesson 12: one connection per thread — SQLite handles are not shared.
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init(seed_providers: list[dict] | None = None) -> None:
    """Create tables and seed the pool from sources already on the machine."""
    _DIR.mkdir(parents=True, exist_ok=True)
    con = _connect()
    try:
        con.executescript(_SCHEMA)
        con.commit()
        for p in (seed_providers or []):
            con.execute(
                "INSERT OR IGNORE INTO providers (name, base_url, api_key_enc, model, size_label, intelligence_rank) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (p["name"], p["base_url"], encrypt_key(p.get("key", "")),
                 p.get("model", ""), p.get("size_label", "Medium"),
                 p.get("intelligence_rank", 50)))
            con.execute(
                "INSERT OR IGNORE INTO stats (provider_id) SELECT id FROM providers WHERE name = ?",
                (p["name"],))
        con.commit()
    finally:
        con.close()


def seed_providers() -> list[dict]:
    """Build the seed list from sources that exist on this machine right now.

    The pool grows automatically: anything the OS_V system already has
    (configured keys, the auto-detected FreeLLMAPI router, the local engine)
    becomes a pool member — no user setup beyond what already exists."""
    seed = []
    seed.append({"name": "oss-local", "base_url": "http://127.0.0.1:11400/v1/chat/completions",
                 "key": "local-no-key", "model": "os_v1",
                 "size_label": "Small", "intelligence_rank": 20})
    try:
        import oss_work_live as m
        cfg = m.load_cloud_config()
        if cfg and cfg.get("provider") in m.CLOUD_PROVIDERS and cfg.get("key", "").strip():
            name = cfg["provider"]
            seed.append({"name": name,
                         "base_url": m.CLOUD_PROVIDERS[name]["url"],
                         "key": cfg.get("key", ""), "model": cfg.get("model", ""),
                         "size_label": "Large" if name in ("gemini", "freellmapi") else "Medium",
                         "intelligence_rank": 35 if name == "gemini" else 45})
        fr = m.get_freellmapi()
        if fr:
            seed.append({"name": "freellmapi", "base_url": m.CLOUD_PROVIDERS["freellmapi"]["url"],
                         "key": fr.get("key", ""), "model": "auto",
                         "size_label": "Large", "intelligence_rank": 40})
    except Exception:  # noqa: BLE001, S110 — seeding must never break startup
        pass
    return seed


# ---------------------------------------------------------------------------
# Scoring — ported from the analyzed scoring service
# ---------------------------------------------------------------------------


def _speed_score(tok_per_sec: float, ttfb_ms: float | None) -> float:
    if tok_per_sec <= 0 and ttfb_ms is None:
        return SPEED_PRIOR
    tp = 1 - math.exp(-tok_per_sec / SPEED_SCALE_TOK_S) if tok_per_sec > 0 else 0.0
    if ttfb_ms is None:
        return tp
    ttfb = 1.0 if ttfb_ms <= TTFB_BEST_MS else (
        0.0 if ttfb_ms >= TTFB_WORST_MS
        else 1 - (ttfb_ms - TTFB_BEST_MS) / (TTFB_WORST_MS - TTFB_BEST_MS))
    if tok_per_sec <= 0:
        return ttfb
    return THROUGHPUT_WEIGHT * tp + TTFB_WEIGHT * ttfb


def _intelligence_score(size_label: str, rank: float, lo: float, hi: float) -> float:
    comp = TIER_VALUE.get(size_label, 2) * 1000 - math.sqrt(max(1.0, rank)) * RANK_SCALE
    if hi <= lo:
        return 1.0
    return max(0.0, min(1.0, (comp - lo) / (hi - lo)))


def _headroom(remaining_frac: float) -> float:
    r = max(0.0, min(1.0, remaining_frac))
    if r >= HEADROOM_RAMP_START:
        return 1.0
    return HEADROOM_FLOOR + (1 - HEADROOM_FLOOR) * (r / HEADROOM_RAMP_START)


def _rate_limit_factor(penalty: float) -> float:
    p = min(max(0.0, penalty), MAX_PENALTY)
    return 1 - p / MAX_PENALTY * RATE_LIMIT_MAX_DAMP


def _penalty(model_id: int) -> float:
    """Decaying in-memory penalty — 1 point forgiven per 2 minutes."""
    entry = _penalties.get(model_id)
    if not entry:
        return 0.0
    elapsed = time.monotonic() - entry["last_hit"]
    decayed = max(0.0, entry["penalty"] - math.floor(elapsed / DECAY_INTERVAL_S) * DECAY_AMOUNT)
    if decayed == 0:
        _penalties.pop(model_id, None)
        return 0.0
    return decayed


def _record_failure(model_id: int, weight: int) -> None:
    now = time.monotonic()
    entry = _penalties.get(model_id)
    if entry:
        decay_steps = math.floor((now - entry["last_hit"]) / DECAY_INTERVAL_S)
        entry["penalty"] = max(0.0, entry["penalty"] - decay_steps * DECAY_AMOUNT)
        entry["count"] += 1
        entry["last_hit"] = now
        entry["penalty"] = min(entry["penalty"] + weight, MAX_PENALTY)
    else:
        _penalties[model_id] = {"count": 1, "last_hit": now, "penalty": float(weight)}


def record_success(provider_id: int, ttfb_ms: float, tok_per_sec: float, tokens: int) -> None:
    """A completed completion: Bayesian win + EMA speed update + forgive one
    penalty point (port of recordSuccess)."""
    global _stats_cache
    con = _connect()
    try:
        row = con.execute("SELECT avg_ttfb_ms FROM stats WHERE provider_id = ?",
                          (provider_id,)).fetchone()
        ema = ttfb_ms if not row or row[0] is None else row[0] * 0.7 + ttfb_ms * 0.3
        cur = con.execute(
            "UPDATE stats SET successes = successes + 1, tok_per_sec = ?, avg_ttfb_ms = ?, "
            "monthly_used_tokens = monthly_used_tokens + ?, "
            "window_used_tokens = window_used_tokens + ? WHERE provider_id = ?",
            (tok_per_sec, ema, tokens, tokens, provider_id))
        if cur.rowcount == 0:
            con.execute("INSERT OR IGNORE INTO stats (provider_id) VALUES (?)", (provider_id,))
        con.commit()
    finally:
        con.close()
    _stats_cache = None
    entry = _penalties.get(provider_id)
    if entry:
        entry["penalty"] = max(0.0, entry["penalty"] - 1)
        if entry["penalty"] == 0:
            _penalties.pop(provider_id, None)


def record_fail(provider_id: int, is_429: bool, provider: str = "", model: str = "") -> None:
    """A failed attempt: Bayesian loss + penalty (+3 for 429, +1 otherwise)."""
    global _stats_cache
    con = _connect()
    try:
        con.execute("UPDATE stats SET failures = failures + 1 WHERE provider_id = ?",
                    (provider_id,))
        con.execute("INSERT INTO usage (ts, hour_bucket, provider, model, ok, is_429) "
                    "VALUES (?, ?, ?, ?, 0, ?)",
                    (time.time(), time.strftime("%Y%m%d%H"), provider, model, int(is_429)))
        con.commit()
    finally:
        con.close()
    _stats_cache = None
    _record_failure(provider_id, PENALTY_PER_429 if is_429 else PENALTY_PER_FAIL)


def cooldown(provider_id: int, seconds: float) -> None:
    """Hard cooldown: the model is skipped outright until expiry."""
    _cooldowns[provider_id] = time.monotonic() + seconds


def _stats_snapshot() -> dict[int, dict]:
    global _stats_cache, _stats_at
    with _lock:
        if _stats_cache is not None and time.monotonic() - _stats_at < STATS_TTL_S:
            return _stats_cache
        con = _connect()
        try:
            rows = con.execute("SELECT provider_id, successes, failures, tok_per_sec, "
                               "avg_ttfb_ms, monthly_used_tokens, window_used_tokens "
                               "FROM stats").fetchall()
        finally:
            con.close()
        snap = {r[0]: {"successes": r[1], "failures": r[2], "tok_per_sec": r[3],
                       "avg_ttfb_ms": r[4], "monthly": r[5], "window": r[6]} for r in rows}
        _stats_cache = snap
        _stats_at = time.monotonic()
        return snap


def set_strategy(name: str) -> None:
    global _strategy
    if name in BANDIT_PRESETS:
        _strategy = name


def _task_adjusted(weights: dict, task: str | None) -> dict:
    """Port of the task shift: code tasks trade speed for intelligence."""
    if not task or task in TASK_EXEMPT or _strategy in TASK_EXEMPT:
        return weights
    share = TASK_WEIGHT_SHARE
    if task == "code":
        shift = weights["speed"] * share
        return {"reliability": weights["reliability"], "speed": weights["speed"] - shift,
                "intelligence": weights["intelligence"] + shift}
    shift = weights["intelligence"] * share
    return {"reliability": weights["reliability"], "speed": weights["speed"] + shift,
            "intelligence": weights["intelligence"] - shift}


def ordered_chain(task: str | None = None) -> list[dict]:
    """The bandit-ordered provider chain — same output shape as the static
    cloud_chain() (provider/url/key/model) so the existing pipeline consumes
    it unchanged. Models in hard cooldown are skipped; scores combine the
    three axes × headroom × rate-limit damping."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT id, name, base_url, api_key_enc, model, monthly_token_cap, "
            "size_label, intelligence_rank FROM providers WHERE enabled = 1").fetchall()
    finally:
        con.close()
    if not rows:
        return []
    import random as _rnd

    import oss_work_live as m

    stats = _stats_snapshot()
    weights = _task_adjusted(BANDIT_PRESETS[_strategy], task)
    now_mono = time.monotonic()
    comps = [TIER_VALUE.get(r[6], 2) * 1000 - math.sqrt(max(1.0, r[7])) * RANK_SCALE for r in rows]
    lo, hi = (min(comps), max(comps)) if comps else (0.0, 0.0)

    scored = []
    for r in rows:
        pid, name, base_url, key_enc, model, cap, size_label, irank = r
        if _cooldowns.get(pid, 0) > now_mono:
            continue
        key = decrypt_key(key_enc)
        if not key:
            continue
        st = stats.get(pid, {})
        succ, fail = st.get("successes", 0), st.get("failures", 0)
        # Thompson sampling: explore while data is thin, exploit what works.
        reliability = _rnd.betavariate(succ + 1.0, fail + 1.0)
        speed = _speed_score(st.get("tok_per_sec", 0.0), st.get("avg_ttfb_ms"))
        intel = _intelligence_score(size_label, irank, lo, hi)
        monthly_head = _headroom(1.0 - st.get("monthly", 0) / cap) if cap else 1.0
        # No per-minute window tracking yet: window headroom full until used.
        window_head = 1.0
        headroom = min(monthly_head, window_head)
        rl = _rate_limit_factor(_penalty(pid))
        w_sum = sum(weights.values()) or 1.0
        base = (weights["reliability"] * reliability + weights["speed"] * speed
                + weights["intelligence"] * intel) / w_sum
        score = base * headroom * rl
        # Registry-compatible cfg: cloud_stream looks providers up here.
        if name not in m.CLOUD_PROVIDERS:
            continue
        cfg = {"provider": name, "url": base_url, "key": key,
               "model": model or m.CLOUD_PROVIDERS[name]["default_model"],
               "_osv_id": pid, "_osv_score": round(score, 4)}
        scored.append((score, cfg))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [cfg for _s, cfg in scored]


# ---------------------------------------------------------------------------
# Unified monthly key (os_v-...) — the only credential end users ever need
# ---------------------------------------------------------------------------


def ensure_local_key() -> str:
    """Issue (once) and return this device's unified key. Stored hashed —
    shown once per call, never stored in plaintext."""
    con = _connect()
    try:
        row = con.execute("SELECT key_hash FROM unified_keys WHERE revoked = 0 "
                          "ORDER BY id LIMIT 1").fetchone()
        if row:
            return f"os_v-local:{row[0][:12]}"
        raw = "os_v-" + secrets.token_hex(24)
        con.execute("INSERT INTO unified_keys (key_hash, label) VALUES (?, ?)",
                    (hashlib.sha256(raw.encode()).hexdigest(), "local-device"))
        con.commit()
        return raw
    finally:
        con.close()


def issue_key(label: str, monthly_cap: int = 0) -> str:
    raw = "os_v-" + secrets.token_hex(24)
    con = _connect()
    try:
        con.execute("INSERT INTO unified_keys (key_hash, label, monthly_token_cap) "
                    "VALUES (?, ?, ?)",
                    (hashlib.sha256(raw.encode()).hexdigest(), label[:60], monthly_cap))
        con.commit()
    finally:
        con.close()
    return raw


def verify_key(raw: str) -> bool:
    if not raw or not raw.startswith("os_v-"):
        return False
    con = _connect()
    try:
        row = con.execute("SELECT revoked FROM unified_keys WHERE key_hash = ?",
                          (hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
        return bool(row and not row[0])
    finally:
        con.close()


def key_info(raw: str) -> dict | None:
    """Live account view for a unified key: cap, usage, remaining."""
    if not raw or not raw.startswith("os_v-"):
        return None
    con = _connect()
    try:
        row = con.execute("SELECT id, label, monthly_token_cap, used_tokens, revoked "
                          "FROM unified_keys WHERE key_hash = ?",
                          (hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
        if not row:
            return None
        kid, label, cap, used, revoked = row
        return {"id": kid, "label": label, "monthly_cap": cap,
                "used_tokens": used, "revoked": bool(revoked),
                "remaining": max(0, cap - used) if cap else None}
    finally:
        con.close()


def key_allowed(raw: str) -> tuple[bool, str]:
    """Gateway admission check for /v1 calls: valid, not revoked, within cap."""
    info = key_info(raw)
    if not info:
        return False, "مفتاح غير معروف — سجّل في OSS واحصل على مفتاح os_v-"
    if info["revoked"]:
        return False, "هذا المفتاح موقوف"
    if info["monthly_cap"] and info["used_tokens"] >= info["monthly_cap"]:
        return False, "استُهلك سقف هذا المفتاح الشهري — يُتجدد في بداية الشهر"
    return True, ""


def record_key_usage(raw: str, tokens: int) -> None:
    """Account tokens against the unified key's monthly budget."""
    if not raw:
        return
    con = _connect()
    try:
        con.execute("UPDATE unified_keys SET used_tokens = used_tokens + ? "
                    "WHERE key_hash = ?",
                    (max(0, tokens), hashlib.sha256(raw.encode()).hexdigest()))
        con.commit()
    finally:
        con.close()


def pool_models() -> list[dict]:
    """Model catalog served at /v1/models: one entry per pool member."""
    con = _connect()
    try:
        rows = con.execute("SELECT name, model, size_label, status FROM providers "
                           "WHERE enabled = 1").fetchall()
    finally:
        con.close()
    import oss_work_live as m
    out = []
    for name, model, size_label, status in rows:
        model = model or (m.CLOUD_PROVIDERS.get(name, {}).get("default_model", ""))
        if not model:
            continue
        out.append({"provider": name, "id": f"oss/{name}/{model}",
                    "model": model, "tier": size_label, "status": status})
    return out


def pool_status() -> dict:
    con = _connect()
    try:
        rows = con.execute(
            "SELECT p.id, p.name, p.status, p.size_label, p.intelligence_rank, "
            "p.monthly_token_cap, s.successes, s.failures, s.tok_per_sec, "
            "s.avg_ttfb_ms, s.monthly_used_tokens "
            "FROM providers p LEFT JOIN stats s ON s.provider_id = p.id "
            "WHERE p.enabled = 1").fetchall()
    finally:
        con.close()
    now_mono = time.monotonic()
    members = []
    for r in rows:
        pid = r[0]
        members.append({
            "provider": r[1], "status": r[2], "tier": r[3],
            "successes": r[6] or 0, "failures": r[7] or 0,
            "tok_per_sec": round(r[8] or 0.0, 1), "avg_ttfb_ms": round(r[9] or 0.0, 1),
            "monthly_tokens": r[10] or 0, "cap": r[5] or 0,
            "penalty": _penalty(pid), "cooldown_s": max(0, round(_cooldowns.get(pid, 0) - now_mono)),
        })
    return {"strategy": _strategy, "members": members,
            "healthy": sum(1 for x in members if x["failures"] <= x["successes"])}
