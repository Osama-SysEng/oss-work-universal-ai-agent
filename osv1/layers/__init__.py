"""The six layers of OS_V1 (spec section 8).

The request flow is: user request → Multimodal Input → World Model and
Memory → Reasoning Engine → Decision Engine → Verifier and Uncertainty
Engine → Adaptive Action Engine → delivered result. When the verifier fails
an output, control returns to reasoning or to evidence gathering.

Each layer lives in its own module here, and the shared context object
carries the state they need.
"""

from __future__ import annotations

__all__ = ["action", "context", "decision", "input_layer", "reasoning", "verifier", "world_model"]
