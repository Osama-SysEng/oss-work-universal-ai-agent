"""System One (SOM): fast, structured, calibrated decisions.

Spec section 9. System One answers typed questions — choice, score, yes/no —
in a single pass without writing prose. It never replaces System Two: the LLM
is used for planning and generation, and the SOM abstains when it is not
confident, so the request falls back to asking the user instead of guessing.

Two backends ship here:

- ``RuleBackend`` (default): a transparent keyword-and-statistics scorer. It
  is fast, offline, and inspectable. It is a heuristic classifier, and it says
  so in every decision it returns.
- ``LayaBackend``: an adapter for a Laya typed-decisions checkpoint served by
  the local engine (spec section 23 names Laya as the SOM base). The weights
  are not bundled; the backend reports ``unavailable`` when no checkpoint is
  configured, and the engine falls back to rules.

Every decision returns a rationale trace and the signals it used, so a
reviewer can check the reasoning instead of trusting a number.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from osv1.calibration import Calibrator
from osv1.contracts import SomDecision

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _word_present(corpus: str, keyword: str) -> bool:
    """True when the keyword appears as a whole word inside the corpus."""
    if not keyword:
        return False
    if keyword.isalnum() or "_" in keyword:
        return re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", corpus) is not None
    return keyword in corpus


@dataclass(frozen=True)
class SomQuestion:
    """A typed question for System One."""

    kind: str  # choice | score | yes_no
    text: str
    labels: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def corpus(self) -> str:
        extra = " ".join(str(v) for v in self.context.values() if isinstance(v, (str, int, float)))
        return f"{self.text} {extra}".lower()


class SomBackend(Protocol):
    """The interface every System One backend implements."""

    name: str

    def answer(self, question: SomQuestion) -> SomDecision: ...


@dataclass
class RuleBackend:
    """Keyword-and-statistics scorer. Deterministic, offline, inspectable."""

    name: str = "rule"
    temperature: float = 0.6

    def answer(self, question: SomQuestion) -> SomDecision:
        if question.kind == "choice":
            return self._choice(question)
        if question.kind == "score":
            return self._score(question)
        if question.kind == "yes_no":
            return self._yes_no(question)
        raise ValueError(f"unsupported question kind: {question.kind}")

    # ── internals ───────────────────────────────────────────────

    def _hits(self, corpus: str, keywords: tuple[str, ...]) -> tuple[int, list[str]]:
        """Count keyword hits on word boundaries.

        Substring matching would score "review" as a hit for the keyword
        "view", so every match has to respect word boundaries.
        """
        matched = [k for k in keywords if k and _word_present(corpus, k.lower())]
        return len(matched), matched

    def _choice(self, question: SomQuestion) -> SomDecision:
        labels = question.labels
        if not labels:
            return SomDecision(
                question_type="choice",
                question=question.text,
                confidence=0.0,
                rationale="no labels supplied",
                source=self.name,
                abstained=True,
            )
        corpus = question.corpus()
        scores: list[float] = []
        signals: list[str] = []
        for label in labels:
            keywords = tuple(question.context.get("keywords", {}).get(label, ()) or ())
            hits, matched = self._hits(corpus, keywords)
            scores.append(float(hits))
            for m in matched:
                signals.append(f"{label}<-{m}")
        if not any(scores):
            prior = 1.0 / len(labels)
            return SomDecision(
                question_type="choice",
                question=question.text,
                value=labels[0],
                probabilities=tuple(prior for _ in labels),
                labels=labels,
                confidence=prior,
                rationale="no keyword signal; fell back to the first label with a uniform prior",
                source=self.name,
                abstained=True,
            )
        # Softmax over raw hit counts, so a label with more supporting
        # keywords wins but the runner-up still carries real probability.
        exponentiated = [math.exp(score / max(self.temperature, 1e-6)) for score in scores]
        total = sum(exponentiated)
        probabilities = tuple(value / total for value in exponentiated)
        best = max(range(len(probabilities)), key=lambda i: probabilities[i])
        confidence = probabilities[best]
        rationale = f"keyword evidence: {', '.join(signals[:8])}" if signals else "keyword evidence"
        return SomDecision(
            question_type="choice",
            question=question.text,
            value=labels[best],
            probabilities=probabilities,
            labels=labels,
            confidence=confidence,
            rationale=rationale,
            source=self.name,
        )

    def _score(self, question: SomQuestion) -> SomDecision:
        levels = question.levels or ("none", "low", "medium", "high", "critical")
        corpus = question.corpus()
        hits = 0
        signals: list[str] = []
        for keyword in question.positive:
            if keyword and _word_present(corpus, keyword.lower()):
                hits += 1
                signals.append(keyword)
        penalty = 0
        for keyword in question.negative:
            if keyword and _word_present(corpus, keyword.lower()):
                penalty += 1
                signals.append(f"-{keyword}")
        index = min(len(levels) - 1, max(0, hits - penalty))
        # Confidence grows with the distance from the middle of the scale.
        confidence = 0.45 + 0.1 * min(3, abs(hits - penalty))
        probabilities = [0.0] * len(levels)
        probabilities[index] = confidence
        remainder = (1.0 - confidence) / max(1, len(levels) - 1)
        for i in range(len(levels)):
            if i != index:
                probabilities[i] = remainder
        return SomDecision(
            question_type="score",
            question=question.text,
            value=levels[index],
            probabilities=tuple(probabilities),
            labels=levels,
            confidence=confidence,
            rationale=f"signals: {', '.join(signals[:8]) or 'none'}",
            source=self.name,
        )

    def _yes_no(self, question: SomQuestion) -> SomDecision:
        corpus = question.corpus()
        pos_hits, pos_matched = self._hits(corpus, question.positive)
        neg_hits, neg_matched = self._hits(corpus, question.negative)
        if not question.positive and not question.negative:
            return SomDecision(
                question_type="yes_no",
                question=question.text,
                value=False,
                probabilities=(0.5, 0.5),
                labels=("no", "yes"),
                confidence=0.5,
                rationale="no features supplied; a coin flip is not a decision",
                source=self.name,
                abstained=True,
            )
        raw = (pos_hits - neg_hits) / max(1, pos_hits + neg_hits)
        probability = 1.0 / (1.0 + math.exp(-4.0 * raw))
        signals = [f"+{m}" for m in pos_matched[:6]] + [f"-{m}" for m in neg_matched[:6]]
        return SomDecision(
            question_type="yes_no",
            question=question.text,
            value=probability >= 0.5,
            probabilities=(1.0 - probability, probability),
            labels=("no", "yes"),
            confidence=abs(probability - 0.5) * 2,
            rationale=f"signals: {', '.join(signals) or 'none'}",
            source=self.name,
        )


@dataclass
class LayaBackend:
    """Adapter for a Laya typed-decisions checkpoint on the local engine.

    The checkpoint is not bundled. Point ``OSS_V1_LAYA_MODEL`` at a served
    model id and the adapter asks for a typed decision over the local engine.
    When the engine is down or the answer does not parse, the runtime falls
    back to the rule backend and records that fact.
    """

    name: str = "laya"
    model: str = ""
    base_url: str = ""
    timeout: float = 60.0
    engine: Any = None

    def available(self) -> bool:
        if not self.model or self.engine is None:
            return False
        try:
            return bool(self.engine.health())
        except Exception:  # noqa: BLE001 - availability check must never raise
            return False

    def answer(self, question: SomQuestion) -> SomDecision:
        if not self.available():
            return SomDecision(
                question_type=question.kind,
                question=question.text,
                confidence=0.0,
                rationale="no Laya checkpoint is served locally",
                source=self.name,
                abstained=True,
            )
        prompt = self._prompt(question)
        try:
            raw = self.engine.chat([{"role": "user", "content": prompt}], max_tokens=300)
        except Exception as exc:  # noqa: BLE001 - fall back honestly
            return SomDecision(
                question_type=question.kind,
                question=question.text,
                confidence=0.0,
                rationale=f"local engine call failed: {exc}",
                source=self.name,
                abstained=True,
            )
        parsed = self._parse(raw.get("content", ""), question)
        if parsed is None:
            return SomDecision(
                question_type=question.kind,
                question=question.text,
                confidence=0.0,
                rationale="the checkpoint did not return a valid typed decision",
                source=self.name,
                abstained=True,
            )
        return parsed

    def _prompt(self, question: SomQuestion) -> str:
        if question.kind == "choice":
            options = ", ".join(question.labels)
            instruction = (
                "Answer with one label from the list and a probability for each label. "
                f"Labels: {options}. Return JSON only: "
                '{"value": "<label>", "probabilities": {"<label>": 0.0}, "rationale": "<short>"}.'
            )
        elif question.kind == "score":
            options = ", ".join(question.levels or ())
            instruction = (
                f"Rate the statement on this scale: {options}. Return JSON only: "
                '{"value": "<level>", "confidence": 0.0, "rationale": "<short>"}.'
            )
        else:
            instruction = (
                "Answer the question with a calibrated probability that it is true. Return JSON only: "
                '{"probability": 0.0, "rationale": "<short>"}.'
            )
        return f"{instruction}\n\nStatement: {question.text}"

    def _parse(self, content: str, question: SomQuestion) -> SomDecision | None:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        rationale = str(data.get("rationale", ""))[:400]
        if question.kind == "choice":
            labels = question.labels
            raw_probs = data.get("probabilities", {})
            probabilities = []
            for label in labels:
                try:
                    probabilities.append(float(raw_probs.get(label, 0.0)))
                except (TypeError, ValueError):
                    probabilities.append(0.0)
            total = sum(probabilities)
            if total <= 0:
                return None
            probabilities = [p / total for p in probabilities]
            value = (
                data.get("value") if data.get("value") in labels else labels[probabilities.index(max(probabilities))]
            )
            confidence = max(probabilities)
            return SomDecision(
                question_type="choice",
                question=question.text,
                value=value,
                probabilities=tuple(probabilities),
                labels=labels,
                confidence=confidence,
                rationale=rationale or "local checkpoint decision",
                source=self.name,
            )
        if question.kind == "score":
            levels = question.levels or ("none", "low", "medium", "high", "critical")
            value = data.get("value") if data.get("value") in levels else levels[0]
            try:
                confidence = float(data.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            probabilities = [0.0] * len(levels)
            probabilities[levels.index(value)] = confidence
            return SomDecision(
                question_type="score",
                question=question.text,
                value=value,
                probabilities=tuple(probabilities),
                labels=levels,
                confidence=confidence,
                rationale=rationale or "local checkpoint decision",
                source=self.name,
            )
        try:
            probability = float(data.get("probability", 0.5))
        except (TypeError, ValueError):
            return None
        probability = min(1.0, max(0.0, probability))
        return SomDecision(
            question_type="yes_no",
            question=question.text,
            value=probability >= 0.5,
            probabilities=(1.0 - probability, probability),
            labels=("no", "yes"),
            confidence=abs(probability - 0.5) * 2,
            rationale=rationale or "local checkpoint decision",
            source=self.name,
        )


@dataclass
class SomEngine:
    """System One with calibration, abstention, and a decision log."""

    backend: SomBackend = field(default_factory=RuleBackend)
    fallback: SomBackend = field(default_factory=RuleBackend)
    calibrator: Calibrator = field(default_factory=Calibrator)
    abstain_threshold: float = 0.6
    log: list[dict[str, Any]] = field(default_factory=list)

    def ask(self, question: SomQuestion, *, record: bool = True) -> SomDecision:
        decision = self.backend.answer(question)
        if decision.abstained and self.backend is not self.fallback:
            fallback_decision = self.fallback.answer(question)
            fallback_decision = self._with_source(
                fallback_decision, f"{decision.source}->fallback:{fallback_decision.source}"
            )
            decision = fallback_decision
        decision = self._calibrate(decision)
        if decision.confidence < self.abstain_threshold and not decision.abstained:
            decision = SomDecision(
                question_type=decision.question_type,
                question=decision.question,
                value=decision.value,
                probabilities=decision.probabilities,
                labels=decision.labels,
                confidence=decision.confidence,
                rationale=decision.rationale + " (below the abstention threshold)",
                source=decision.source,
                abstained=True,
            )
        if record:
            self.log.append(decision.as_dict())
        return decision

    def _calibrate(self, decision: SomDecision) -> SomDecision:
        if self.calibrator.temperature == 1.0 or not decision.probabilities:
            return decision
        adjusted = tuple(self.calibrator.apply(p) for p in decision.probabilities)
        total = sum(adjusted) or 1.0
        normalized = tuple(p / total for p in adjusted)
        confidence = max(normalized) if normalized else decision.confidence
        return SomDecision(
            question_type=decision.question_type,
            question=decision.question,
            value=decision.value,
            probabilities=normalized,
            labels=decision.labels,
            confidence=confidence,
            rationale=decision.rationale,
            source=decision.source,
            abstained=decision.abstained,
        )

    @staticmethod
    def _with_source(decision: SomDecision, source: str) -> SomDecision:
        return SomDecision(
            question_type=decision.question_type,
            question=decision.question,
            value=decision.value,
            probabilities=decision.probabilities,
            labels=decision.labels,
            confidence=decision.confidence,
            rationale=decision.rationale,
            source=source,
            abstained=decision.abstained,
        )

    def stats(self) -> dict[str, Any]:
        total = len(self.log)
        abstained = sum(1 for entry in self.log if entry.get("abstained"))
        avg_confidence = sum(entry.get("confidence", 0.0) for entry in self.log) / total if total else 0.0
        return {
            "backend": getattr(self.backend, "name", "unknown"),
            "decisions": total,
            "abstained": abstained,
            "abstention_rate": round(abstained / total, 4) if total else 0.0,
            "avg_confidence": round(avg_confidence, 4),
            "calibration": self.calibrator.as_dict(),
        }


def build_som(
    *,
    engine: Any = None,
    laya_model: str = "",
    abstain_threshold: float = 0.6,
    calibrator: Calibrator | None = None,
) -> SomEngine:
    """Build System One, preferring a local Laya checkpoint when one is served."""
    rule = RuleBackend()
    backend: SomBackend = rule
    if laya_model and engine is not None:
        laya = LayaBackend(model=laya_model, engine=engine)
        if laya.available():
            backend = laya
    return SomEngine(
        backend=backend,
        fallback=rule,
        calibrator=calibrator or Calibrator(),
        abstain_threshold=abstain_threshold,
    )


SomObserver = Callable[[SomDecision], None]
