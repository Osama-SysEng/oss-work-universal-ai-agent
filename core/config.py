"""
OSS Work — Configuration.

Supports multiple modes:
- telegram: link the agent to Telegram (phone<->desktop)
- desktop: standalone agent on the desktop (CLI or API)
- hybrid: both modes together
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "OSS Work"
VERSION = "0.3.0"
ALLOWED_ROOT = "./data"
DATA_DIR = "./data"


# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════


@dataclass
class AgentConfig:
    """Agent runtime settings."""

    # ── Mode ──
    mode: str = "desktop"  # 'telegram' | 'desktop' | 'hybrid'
    telegram_enabled: bool = False  # Enable the Telegram link
    bot_token: str | None = None  # Telegram bot token
    bot_username: str | None = None  # Bot name (e.g. @oss_work_bot)

    # ── Desktop ──
    desktop_mode: str = "cli"  # 'cli' | 'api' | 'gui'
    api_enabled: bool = True  # Enable the local API
    api_host: str = "127.0.0.1"  # API host
    api_port: int = 8080  # API port

    # ── Data ──
    data_dir: str = "./data/oss-work"
    db_path: str | None = None
    use_memory_db: bool = True
    allowed_root: str = "./data"

    # ── Simulation / Production ──
    simulation_only: bool = True  # Simulation-only by default
    approved_actions: bool = False  # Approval required for real operations

    # ── Agent Processing ──
    max_threads: int = 1000
    invention_enabled: bool = True
    simulation_depth: int = 100

    # ── Security ──
    allow_file_ops: bool = False
    allow_code_exec: bool = False
    allow_browser: bool = False
    allow_external: bool = False

    # ── JEV / TypeSafe AI ──
    use_jev: bool = False  # Enable the JEV model for classification and ranking
    jev_api_key: str | None = None  # API key from TypeSafe (ts_...)
    jev_base_url: str = "https://api.typesafe.ai/v1"
    jev_model: str = "jev-latest"  # 'jev-latest' | 'jev-1.13.0' | ...
    jev_timeout: int = 30  # seconds

    # ── Logging ──
    log_level: str = "INFO"
    log_to_file: bool = False
    log_dir: str = "./logs"

    def __post_init__(self):
        if self.db_path is None:
            self.db_path = str(Path(self.data_dir) / "tasks.db")
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

    def is_telegram_mode(self) -> bool:
        return self.mode == "telegram" or (self.mode == "hybrid" and self.telegram_enabled)

    def is_desktop_mode(self) -> bool:
        return self.mode == "desktop" or self.mode == "hybrid"

    def is_hybrid_mode(self) -> bool:
        return self.mode == "hybrid"


# ═══════════════════════════════════════════════════════════════════
# Loading
# ═══════════════════════════════════════════════════════════════════


def load_config(env_path: str | Path | None = None) -> AgentConfig:
    """Load settings from .env or environment variables."""
    config = AgentConfig()

    if env_path is None:
        candidates = [
            Path.cwd() / ".env",
            PROJECT_ROOT / ".env",
        ]
        for c in candidates:
            if c.exists():
                env_path = c
                break

    if env_path and Path(env_path).exists():
        _load_from_env_file(config, Path(env_path))
    else:
        _load_from_env_vars(config)

    return config


def _load_from_env_file(config: AgentConfig, path: Path) -> None:
    """Load from a .env file."""
    try:
        from dotenv import load_dotenv

        load_dotenv(str(path), override=False)
    except ImportError:
        pass

    def _int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)) or default)
        except (TypeError, ValueError):
            return default

    # Mode
    mode = os.getenv("OSS_WORK_MODE", "").strip()
    if mode:
        config.mode = mode

    # Telegram
    config.telegram_enabled = os.getenv("OSS_TELEGRAM_ENABLED", "").lower() == "true"
    config.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    config.bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip() or None

    # Desktop
    dm = os.getenv("OSS_DESKTOP_MODE", "").strip()
    if dm:
        config.desktop_mode = dm
    config.api_enabled = os.getenv("OSS_API_ENABLED", "true").lower() == "true"
    config.api_host = os.getenv("OSS_API_HOST", "127.0.0.1")
    config.api_port = _int("OSS_API_PORT", 8080)

    # Data
    config.data_dir = os.getenv("OSS_WORK_DATA_DIR", config.data_dir)
    config.db_path = os.getenv("OSS_WORK_DB_PATH", config.db_path)
    config.allowed_root = os.getenv("OSS_WORK_ALLOWED_ROOT", config.allowed_root)

    # Simulation
    config.simulation_only = os.getenv("OSS_WORK_SIMULATION_ONLY", "1") == "1"
    config.approved_actions = os.getenv("OSS_APPROVED_ACTIONS", "").lower() == "true"

    # Agent settings
    config.max_threads = _int("OSS_MAX_THREADS", 1000)
    config.invention_enabled = os.getenv("OSS_INVENTION_ENABLED", "true").lower() == "true"
    config.simulation_depth = _int("OSS_SIMULATION_DEPTH", 100)

    # Security
    config.allow_file_ops = os.getenv("OSS_ALLOW_FILE_OPS", "false").lower() == "true"
    config.allow_code_exec = os.getenv("OSS_ALLOW_CODE_EXEC", "false").lower() == "true"
    config.allow_browser = os.getenv("OSS_ALLOW_BROWSER", "false").lower() == "true"
    config.allow_external = os.getenv("OSS_ALLOW_EXTERNAL", "false").lower() == "true"

    # JEV / TypeSafe AI
    config.jev_api_key = os.getenv("TYPESAFE_API_KEY", "").strip() or config.jev_api_key
    config.use_jev = os.getenv("OSS_USE_JEV", "").lower() == "true" or config.use_jev
    config.jev_base_url = os.getenv("OSS_JEV_BASE_URL", config.jev_base_url)
    config.jev_model = os.getenv("OSS_JEV_MODEL", config.jev_model)
    config.jev_timeout = _int("OSS_JEV_TIMEOUT", config.jev_timeout)

    # Logging (OSS_LOG_LEVEL with OSS_WORK_LOG_LEVEL alias)
    config.log_level = os.getenv("OSS_LOG_LEVEL", "") or os.getenv("OSS_WORK_LOG_LEVEL", "") or config.log_level
    config.log_to_file = os.getenv("OSS_LOG_TO_FILE", "false").lower() == "true"
    config.log_dir = os.getenv("OSS_LOG_DIR", config.log_dir)


def _load_from_env_vars(config: AgentConfig) -> None:
    """Load from environment variables only."""
    _load_from_env_file(config, Path("/dev/null"))


# ═══════════════════════════════════════════════════════════════════
# .ENV Template
# ═══════════════════════════════════════════════════════════════════

ENV_TEMPLATE = """\
# ═══════════════════════════════════════════════════════════════════
# OSS Work — Configuration (.env)
# ═══════════════════════════════════════════════════════════════════
#
# Available modes:
#   desktop  — Standalone agent on the desktop (CLI + local API)
#   telegram — Link the agent to Telegram (phone<->desktop)
#   hybrid   — Both modes together
OSS_WORK_MODE=desktop

# ═══════════════════════════════════════════════════════════════════
# TELEGRAM (for linking phone and desktop)
# ═══════════════════════════════════════════════════════════════════
# Get the token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=

# Enable the Telegram link
OSS_TELEGRAM_ENABLED=false

# ═══════════════════════════════════════════════════════════════════
# DESKTOP / LOCAL API
# ═══════════════════════════════════════════════════════════════════
OSS_DESKTOP_MODE=cli        # cli | api | gui
OSS_API_ENABLED=true        # Enable the local API (like any other AI model)
OSS_API_HOST=127.0.0.1
OSS_API_PORT=8080

# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
OSS_WORK_DATA_DIR=./data/oss-work
OSS_WORK_DB_PATH=./data/oss-work/tasks.db
OSS_LOG_TO_FILE=false
OSS_LOG_DIR=./logs

# ═══════════════════════════════════════════════════════════════════
# SIMULATION / PRODUCTION
# ═══════════════════════════════════════════════════════════════════
OSS_WORK_SIMULATION_ONLY=1      # 0 = production, 1 = simulation
OSS_APPROVED_ACTIONS=false      # Approval required for real operations

# ═══════════════════════════════════════════════════════════════════
# AGENT SETTINGS
# ═══════════════════════════════════════════════════════════════════
OSS_MAX_THREADS=1000
OSS_INVENTION_ENABLED=true
OSS_SIMULATION_DEPTH=100

# ═══════════════════════════════════════════════════════════════════
# SECURITY (advanced — use with caution)
# ═══════════════════════════════════════════════════════════════════
OSS_ALLOW_FILE_OPS=false
OSS_ALLOW_CODE_EXEC=false
OSS_ALLOW_BROWSER=false
OSS_ALLOW_EXTERNAL=false

# ═══════════════════════════════════════════════════════════════════
# JEV / TypeSafe AI
# ═══════════════════════════════════════════════════════════════════
# https://typesafe.ai — System One model for classification and ranking
# Get the key from: https://console.typesafe.ai
TYPESAFE_API_KEY=              # ts_... — leave empty if you are not connected to JEV
OSS_USE_JEV=false              # true = enable JEV for classification and ranking
OSS_JEV_MODEL=jev-latest       # jev-latest | jev-1.13.0 | ...
OSS_JEV_BASE_URL=https://api.typesafe.ai/v1
OSS_JEV_TIMEOUT=30

# ═══════════════════════════════════════════════════════════════════
# API RATE LIMIT
# ═══════════════════════════════════════════════════════════════════
OSS_RATE_LIMIT=60
OSS_RATE_WINDOW=60

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════
OSS_LOG_LEVEL=INFO
"""


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def show_config() -> None:
    """Show the current settings."""
    config = load_config()
    print(f"\n{'=' * 60}")
    print("  OSS Work — Current Configuration")
    print(f"{'=' * 60}")
    print(f"  Mode:           {config.mode}")
    print(f"  Telegram:       {'✅ Enabled' if config.telegram_enabled and config.bot_token else '❌ Not configured'}")
    print(f"  Desktop:        {config.desktop_mode} ({'API' if config.api_enabled else 'CLI'})")
    if config.api_enabled:
        print(f"  API URL:        http://{config.api_host}:{config.api_port}")
    print(f"  Simulation:     {'ON' if config.simulation_only else 'OFF'}")
    print(f"  Data Dir:       {config.data_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    show_config()
