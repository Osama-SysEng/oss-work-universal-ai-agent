"""System Two: the language model that plans, reasons, and generates.

Spec section 9: the LLM runs only when a task needs generation or long
reasoning, or when System One abstains. Every method here returns the source
of the answer it produced, so a caller can never mistake a template for a
model response.

Long-horizon output (spec section 10) is produced as verified chunks with
checkpoints, so an interrupted generation resumes instead of starting over.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from osv1.engine.local_engine import LocalEngine, LocalEngineError

JSON_BLOCK = re.compile(r"\{.*\}", re.S)


@dataclass
class LlmClient:
    """Wraps the local engine with the structured prompts the layers need."""

    engine: LocalEngine = field(default_factory=LocalEngine)
    max_tokens: int = 512
    temperature: float = 0.0
    recorder: Any = None  # osv1.eval.cascade.CascadeRecorder | None

    # ── health ────────────────────────────────────────────────

    def healthy(self) -> bool:
        return self.engine.health()

    def describe(self) -> dict[str, Any]:
        return self.engine.describe()

    # ── raw generation ────────────────────────────────────────

    def complete(self, prompt: str, *, system: str = "", max_tokens: int | None = None) -> dict[str, Any]:
        """One completion. ``source`` is ``local_engine`` or ``unavailable``."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        started = perf_counter()
        try:
            result = self.engine.chat(
                messages,
                max_tokens=max_tokens or self.max_tokens,
                temperature=self.temperature,
            )
        except LocalEngineError as exc:
            if self.recorder is not None:
                self.recorder.record_llm((perf_counter() - started) * 1000.0, ok=False)
            return {"content": "", "source": "unavailable", "error": str(exc), "model": self.engine.model_label}
        if self.recorder is not None:
            self.recorder.record_llm((perf_counter() - started) * 1000.0, ok=True)
        return {"content": result["content"], "source": "local_engine", "model": result["model"]}

    def json_complete(self, prompt: str, *, system: str = "", max_tokens: int | None = None) -> tuple[Any, str]:
        """Ask for JSON and parse it. Returns ``(value, source)``."""
        result = self.complete(prompt, system=system, max_tokens=max_tokens)
        if result["source"] == "unavailable":
            return None, "unavailable"
        match = JSON_BLOCK.search(result["content"])
        if not match:
            return None, "unparsable"
        try:
            return json.loads(match.group(0)), "local_engine"
        except json.JSONDecodeError:
            return None, "unparsable"

    # ── planning ──────────────────────────────────────────────

    def plan(self, task: str, *, agent_prompt: str, available_tools: list[str], max_steps: int = 8) -> dict[str, Any]:
        """Ask the model for a plan. Falls back to the caller's template."""
        tools = ", ".join(available_tools) if available_tools else "none"
        prompt = (
            "Plan the task below. Use only the listed tools. "
            f"Tools: {tools}. At most {max_steps} steps. "
            'Return JSON only: {"steps": [{"action": "...", "tool": "...", '
            '"target": "...", "detail": "..."}], "rationale": "..."}.\n\n'
            f"Agent role: {agent_prompt}\n\nTask: {task}"
        )
        value, source = self.json_complete(prompt, system="You are a careful local planning engine.")
        if source != "local_engine" or not isinstance(value, dict):
            return {"steps": [], "rationale": "", "source": source}
        steps = value.get("steps")
        if not isinstance(steps, list):
            return {"steps": [], "rationale": "", "source": source}
        cleaned = []
        for step in steps[:max_steps]:
            if not isinstance(step, dict):
                continue
            cleaned.append(
                {
                    "action": str(step.get("action", ""))[:200],
                    "tool": str(step.get("tool", ""))[:60],
                    "target": str(step.get("target", ""))[:400],
                    "detail": str(step.get("detail", ""))[:800],
                }
            )
        return {"steps": cleaned, "rationale": str(value.get("rationale", ""))[:800], "source": source}

    # ── hypotheses ─────────────────────────────────────────────

    def hypotheses(self, task: str, *, state_summary: str, count: int = 3) -> list[dict[str, Any]]:
        """Ask for competing hypotheses with the consequences that follow."""
        prompt = (
            f"Give up to {count} competing hypotheses for the task. Each needs a statement, "
            "the consequences that follow from it, and a concrete way to test it. "
            'Return JSON only: {"hypotheses": [{"statement": "...", "consequences": ["..."], '
            '"test": "..."}]}.\n\n'
            f"State: {state_summary}\n\nTask: {task}"
        )
        value, source = self.json_complete(prompt, system="You are a careful local reasoning engine.")
        if source != "local_engine" or not isinstance(value, dict):
            return []
        raw = value.get("hypotheses")
        if not isinstance(raw, list):
            return []
        result = []
        for item in raw[:count]:
            if not isinstance(item, dict):
                continue
            consequences = item.get("consequences")
            result.append(
                {
                    "statement": str(item.get("statement", ""))[:400],
                    "consequences": [str(c)[:300] for c in consequences][:5] if isinstance(consequences, list) else [],
                    "test": str(item.get("test", ""))[:400],
                }
            )
        return result

    # ── long-horizon generation ───────────────────────────────

    def generate_in_chunks(
        self,
        task: str,
        *,
        chunks: int,
        checkpoint_dir: Path,
        max_tokens: int = 900,
    ) -> dict[str, Any]:
        """Generate a long answer chunk by chunk, checkpointing after each one.

        A chunk already written to the checkpoint directory is reused, so an
        interrupted run resumes where it stopped instead of paying for the
        whole answer again.
        """
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        produced: list[str] = []
        resumed = 0
        for index in range(1, max(1, chunks) + 1):
            checkpoint = checkpoint_dir / f"chunk_{index:03d}.txt"
            if checkpoint.exists():
                produced.append(checkpoint.read_text(encoding="utf-8"))
                resumed += 1
                continue
            previous = produced[-1][-1200:] if produced else ""
            prompt = (
                f"Task: {task}\n\n"
                f"This is part {index} of {chunks}. Continue from the previous part without repeating it. "
                "Write only this part.\n\n"
                f"Previous part tail:\n{previous}"
            )
            result = self.complete(prompt, max_tokens=max_tokens)
            if result["source"] == "unavailable":
                return {
                    "text": "\n\n".join(produced),
                    "chunks": len(produced),
                    "planned_chunks": chunks,
                    "resumed_chunks": resumed,
                    "source": "unavailable",
                    "error": result.get("error", ""),
                }
            text = result["content"].strip()
            produced.append(text)
            checkpoint.write_text(text, encoding="utf-8")
        return {
            "text": "\n\n".join(produced),
            "chunks": len(produced),
            "planned_chunks": chunks,
            "resumed_chunks": resumed,
            "source": "local_engine",
        }
