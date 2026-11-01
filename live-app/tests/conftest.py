"""pytest discovery for live-app tests (run from the repo root or here)."""
import sys
from pathlib import Path

LIVE_APP = str(Path(__file__).resolve().parent.parent)
if LIVE_APP not in sys.path:
    sys.path.insert(0, LIVE_APP)
