"""
OSS Work — Configuration.

يدعم أوضاع متعددة:
- telegram: ربط الوكيل بالتلجرام (الهاتف↔桌面)
- desktop: الوكيل المستقل على桌面 (CLI أو API)
- hybrid: كلا الوضعين معًا
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


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
    """إعدادات运行 الوكيل."""

    # ── Mode ──
    mode: str = "desktop"           # 'telegram' | 'desktop' | 'hybrid'
    telegram_enabled: bool = False  # تفعيل ربط التلجرام
    bot_token: str | None = None    # توكن بوت التلجرام
    bot_username: str | None = None # اسم البوت (مثلاً @oss_work_bot)

    # ── Desktop ──
    desktop_mode: str = "cli"       # 'cli' | 'api' | 'gui'
    api_enabled: bool = True        # تفعيل API محلي (بالتناقض مع المستخدم)
    api_host: str = "127.0.0.1"     # مض tribut API
    api_port: int = 8080            # منفذ API

    # ── Data ──
    data_dir: str = "./data/oss-work"
    db_path: str | None = None
    use_memory_db: bool = True
    allowed_root: str = "./data"

    # ── Simulation / Production ──
    simulation_only: bool = True    # محاكاة فقط افتراضيًا
    approved_actions: bool = False  # Approval مطلوب للعمليات الحقيقية

    # ── Agent Processing ──
    max_threads: int = 1000
    invention_enabled: bool = True
    simulation_depth: int = 100

    # ── Security ──
    allow_file_ops: bool = False
    allow_code_exec: bool = False
    allow_browser: bool = False
    allow_external: bool = False

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
        return self.mode == "telegram" or (
            self.mode == "hybrid" and self.telegram_enabled
        )

    def is_desktop_mode(self) -> bool:
        return self.mode == "desktop" or self.mode == "hybrid"

    def is_hybrid_mode(self) -> bool:
        return self.mode == "hybrid"


# ═══════════════════════════════════════════════════════════════════
# Loading
# ═══════════════════════════════════════════════════════════════════

def load_config(env_path: str | Path | None = None) -> AgentConfig:
    """تحميل الإعدادات من .env أو متغيرات البيئة."""
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
    """تحميل من ملف .env."""
    try:
        from dotenv import load_dotenv
        load_dotenv(str(path), override=False)
    except ImportError:
        pass

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
    config.api_port = int(os.getenv("OSS_API_PORT", "8080") or 8080)

    # Data
    config.data_dir = os.getenv("OSS_WORK_DATA_DIR", config.data_dir)
    config.db_path = os.getenv("OSS_WORK_DB_PATH", config.db_path)

    # Simulation
    config.simulation_only = os.getenv("OSS_WORK_SIMULATION_ONLY", "1") == "1"
    config.approved_actions = os.getenv("OSS_APPROVED_ACTIONS", "").lower() == "true"

    # Agent settings
    config.max_threads = int(os.getenv("OSS_MAX_THREADS", "1000") or 1000)
    config.invention_enabled = os.getenv("OSS_INVENTION_ENABLED", "true").lower() == "true"
    config.simulation_depth = int(os.getenv("OSS_SIMULATION_DEPTH", "100") or 100)

    # Security
    config.allow_file_ops = os.getenv("OSS_ALLOW_FILE_OPS", "false").lower() == "true"
    config.allow_code_exec = os.getenv("OSS_ALLOW_CODE_EXEC", "false").lower() == "true"
    config.allow_browser = os.getenv("OSS_ALLOW_BROWSER", "false").lower() == "true"
    config.allow_external = os.getenv("OSS_ALLOW_EXTERNAL", "false").lower() == "true"

    # Logging
    config.log_level = os.getenv("OSS_LOG_LEVEL", "INFO")
    config.log_to_file = os.getenv("OSS_LOG_TO_FILE", "false").lower() == "true"


def _load_from_env_vars(config: AgentConfig) -> None:
    """تحميل من متغيرات البيئة فقط."""
    _load_from_env_file(config, Path("/dev/null"))


# ═══════════════════════════════════════════════════════════════════
# .ENV Template
# ═══════════════════════════════════════════════════════════════════

ENV_TEMPLATE = """\
# ═══════════════════════════════════════════════════════════════════
# OSS Work — Configuration (.env)
# ═══════════════════════════════════════════════════════════════════
#
# الأوضاع المتاحة:
#   desktop  — الوكيل المستقل على桌面 (CLI + API محلي)
#   telegram — ربط الوكيل بالتلجرام (الهاتف↔桌面)
#   hybrid   — كلا الوضعين معًا
OSS_WORK_MODE=desktop

# ═══════════════════════════════════════════════════════════════════
# TELEGRAM (لربط الهاتف桌面)
# ═══════════════════════════════════════════════════════════════════
# احصل على التوكن من @BotFather على التلجرام
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=

# تفعيل ربط التلجرام
OSS_TELEGRAM_ENABLED=false

# ═══════════════════════════════════════════════════════════════════
# DESKTOP / LOCAL API
# ═══════════════════════════════════════════════════════════════════
OSS_DESKTOP_MODE=cli        # cli | api | gui
OSS_API_ENABLED=true        # تفعيل API محلي (مثل أي نموذج ذكاء اصطناعي)
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
OSS_WORK_SIMULATION_ONLY=1      # 0 = إنتاج، 1 = محاكاة
OSS_APPROVED_ACTIONS=false      # موافقة مطلوبة للعمليات الحقيقية

# ═══════════════════════════════════════════════════════════════════
# AGENT SETTINGS
# ═══════════════════════════════════════════════════════════════════
OSS_MAX_THREADS=1000
OSS_INVENTION_ENABLED=true
OSS_SIMULATION_DEPTH=100

# ═══════════════════════════════════════════════════════════════════
# SECURITY (متقدم — استخدم بحذر)
# ═══════════════════════════════════════════════════════════════════
OSS_ALLOW_FILE_OPS=false
OSS_ALLOW_CODE_EXEC=false
OSS_ALLOW_BROWSER=false
OSS_ALLOW_EXTERNAL=false

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════
OSS_LOG_LEVEL=INFO
"""


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def show_config() -> None:
    """عرض الإعدادات الحالية."""
    config = load_config()
    print(f"\n{'='*60}")
    print(f"  OSS Work — Current Configuration")
    print(f"{'='*60}")
    print(f"  Mode:           {config.mode}")
    print(f"  Telegram:       {'✅ Enabled' if config.telegram_enabled and config.bot_token else '❌ Not configured'}")
    print(f"  Desktop:        {config.desktop_mode} ({'API' if config.api_enabled else 'CLI'})")
    if config.api_enabled:
        print(f"  API URL:        http://{config.api_host}:{config.api_port}")
    print(f"  Simulation:     {'ON' if config.simulation_only else 'OFF'}")
    print(f"  Data Dir:       {config.data_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    show_config()
