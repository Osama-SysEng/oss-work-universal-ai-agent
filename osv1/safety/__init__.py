"""Safety layer for OS_V1 (spec section 19).

The specification calls this layer mandatory: it sits under every other
component and the system itself may not change it. The files in this package
implement it:

- ``permissions``: explicit, revocable scopes for files, network, programs,
  and irreversible actions.
- ``approvals``: human approval for irreversible actions.
- ``audit``: a hash-chained log of every action and every self-evolution step.
- ``killswitch``: an instant stop.
- ``injection``: content from files, web pages, and tools is data, never an
  instruction.
- ``secrets``: no secret is stored in plain text.
"""

from __future__ import annotations

__all__ = ["approvals", "audit", "injection", "killswitch", "permissions", "secrets"]
