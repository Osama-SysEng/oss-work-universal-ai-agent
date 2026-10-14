"""oss-work OS configuration (v1): local-only single system, no keys, no cloud."""

from __future__ import annotations

import os as _stdlib_os

OS_VERSION = "1.0.0"
OS_NAME = "oss-work OS"


def _env_bool(name: str, default: bool) -> bool:
    raw = _stdlib_os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Strict local-only mode: the router may only use LOCAL providers and the
# local fallback. Cloud/API keys are ignored even if present.
OS_STRICT: bool = _env_bool("OSS_OS_STRICT", True)

# Local inference engine (llama.cpp llama-server, OpenAI-compatible).
LOCAL_URL: str = _stdlib_os.getenv("OSS_LOCAL_URL", "http://127.0.0.1:11400").rstrip("/")
LOCAL_MODEL: str = _stdlib_os.getenv("OSS_LOCAL_MODEL", "qwen2.5-3b-q4_k_m")
LOCAL_TIMEOUT: float = float(_stdlib_os.getenv("OSS_LOCAL_TIMEOUT", "120"))

# On-disk state (SQLite + skills + workspace). Overridable for tests.
DATA_DIR: str = _stdlib_os.getenv("OSS_OS_DATA_DIR", "./data-os")
SKILLS_DIR: str = _stdlib_os.getenv("OSS_OS_SKILLS_DIR", "./skills-os")
WORKSPACE_DIR: str = _stdlib_os.getenv("OSS_OS_WORKSPACE_DIR", "./workspace")

# Local hosting bind (loopback only — this OS never exposes LAN/WAN by itself).
HOST: str = "127.0.0.1"


def data_dir() -> str:
    return _stdlib_os.getenv("OSS_OS_DATA_DIR", DATA_DIR)


def db_path() -> str:
    return _stdlib_os.path.join(data_dir(), "os.db")


def skills_dir() -> str:
    return _stdlib_os.getenv("OSS_OS_SKILLS_DIR", SKILLS_DIR)


def workspace_dir() -> str:
    return _stdlib_os.getenv("OSS_OS_WORKSPACE_DIR", WORKSPACE_DIR)
