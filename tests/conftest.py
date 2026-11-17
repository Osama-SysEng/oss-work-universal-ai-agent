"""Make the live-app modules importable for the root test suite."""
import sys
from pathlib import Path

LIVE_APP = str(Path(__file__).resolve().parent.parent / "live-app")
if LIVE_APP not in sys.path:
    sys.path.insert(0, LIVE_APP)
