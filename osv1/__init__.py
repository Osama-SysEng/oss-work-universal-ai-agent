"""OSS Work / OS_V1 — the unified local model runtime.

The package implements the six-layer architecture described in the OS_V1
specification (sections 8-21): multimodal input, world model and memory,
reasoning, decision, independent verification, and adaptive action.

Every component is local-first: no provider account, no API key, no network
requirement for the core path.
"""

from __future__ import annotations

from osv1.config import MODEL_NAME, PRODUCT, VERSION

__all__ = ["MODEL_NAME", "PRODUCT", "VERSION"]
