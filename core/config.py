"""Runtime configuration for the safe local-first release."""
from __future__ import annotations

import os
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "OSS-Work"
VERSION = "0.2.0-safe"
OS_NAME = platform.system().lower()
ARCH = platform.machine()
DATA_DIR = Path(os.getenv("OSS_WORK_DATA_DIR", PROJECT_ROOT / "data")).expanduser().resolve()
LOG_DIR = DATA_DIR / "logs"
ALLOWED_ROOT = Path(os.getenv("OSS_WORK_ALLOWED_ROOT", DATA_DIR)).expanduser().resolve()

POLICY = {
    "simulation_only": os.getenv("OSS_WORK_SIMULATION_ONLY", "1") not in {"0", "false", "no"},
    "allow_code_execution": False,
    "require_approval_for_mutation": True,
    "require_approval_for_external_io": True,
    "max_file_bytes": int(os.getenv("OSS_WORK_MAX_FILE_BYTES", "1048576")),
    "max_output_bytes": int(os.getenv("OSS_WORK_MAX_OUTPUT_BYTES", "65536")),
}


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
