"""The kill switch (spec section 19).

An instant stop that halts every activity: the action engine refuses to run
tools, the scheduler stops submitting work, and the interface shows the state.

The switch is a file, so it works across processes: any component can check
it, and the user can also create it by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class KillSwitch:
    """A file-backed stop signal."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/kill.switch"))

    def engaged(self) -> bool:
        return self.path.exists()

    def engage(self, reason: str = "requested by the user") -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json_line({"reason": reason, "at": datetime.now(UTC).isoformat()}),
            encoding="utf-8",
        )
        return self.path

    def release(self) -> bool:
        """Release the switch. Returns True when a switch was actually there."""
        if not self.path.exists():
            return False
        self.path.unlink()
        return True

    def status(self) -> dict[str, object]:
        if not self.engaged():
            return {"engaged": False}
        return {"engaged": True, "detail": self.path.read_text(encoding="utf-8", errors="replace").strip()}


def json_line(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False) + "\n"
