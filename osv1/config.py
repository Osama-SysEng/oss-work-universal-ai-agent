"""OS_V1 configuration: device tiers, limits, local paths, safety switches.

Spec reference: section 23 (technical decisions) for the device tiers and
context windows, section 19 for the safety switches, section 6 for the
independence rules (nothing here may require a network or a key).
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass, field
from pathlib import Path

PRODUCT = "OSS Work"
MODEL_NAME = "OS_V1"
VERSION = "1.0.0"


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class DeviceTier:
    """One planning tier from spec section 23 (targets, confirmed by benchmark)."""

    key: str
    label: str
    context_tokens: int
    min_ram_gb: int
    vram_gb: int
    note: str
    # How long one inference call may take on this hardware. A CPU-served
    # model needs far longer than a GPU one, and a fixed 120-second default
    # measured at 27 % timeouts on the Lite tier (docs/EVALUATION.md) — so
    # the timeout belongs to the tier, not to the code.
    inference_timeout_s: float = 120.0


DEVICE_TIERS: dict[str, DeviceTier] = {
    "lite": DeviceTier(
        key="lite",
        label="Lite",
        context_tokens=128_000,
        min_ram_gb=16,
        vram_gb=0,
        note="16 GB RAM, no GPU, small quantized models.",
        inference_timeout_s=300.0,
    ),
    "standard": DeviceTier(
        key="standard",
        label="Standard",
        context_tokens=256_000,
        min_ram_gb=32,
        vram_gb=12,
        note="32 GB RAM, 12-16 GB VRAM GPU.",
        inference_timeout_s=120.0,
    ),
    "pro": DeviceTier(
        key="pro",
        label="Pro",
        context_tokens=1_000_000,
        min_ram_gb=64,
        vram_gb=24,
        note="64 GB RAM, 24 GB+ VRAM GPU, or a user-owned server.",
        inference_timeout_s=60.0,
    ),
}


def total_ram_gb() -> float:
    """Total physical RAM in GiB. Uses the Windows API; 0.0 when unknown."""
    if os.name != "nt":
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round(pages * page_size / (1024**3), 1)
        except (ValueError, OSError, AttributeError):
            return 0.0

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError):
        return 0.0
    return round(status.ullTotalPhys / (1024**3), 1)


def detect_tier() -> DeviceTier:
    """Pick a tier from RAM. VRAM needs an explicit override, so it never guesses."""
    override = os.getenv("OSS_V1_TIER", "").strip().lower()
    if override in DEVICE_TIERS:
        return DEVICE_TIERS[override]
    ram = total_ram_gb()
    if ram and ram < 24:
        return DEVICE_TIERS["lite"]
    if ram and ram < 48:
        return DEVICE_TIERS["standard"]
    return DEVICE_TIERS["standard"] if ram else DEVICE_TIERS["lite"]


@dataclass
class Settings:
    """Runtime settings. All paths are local; no value here points to a provider."""

    data_dir: Path = field(default_factory=lambda: Path(os.getenv("OSS_V1_DATA_DIR", "./data-osv1")))
    workspace_dir: Path = field(default_factory=lambda: Path(os.getenv("OSS_V1_WORKSPACE_DIR", "./workspace")))
    skills_dir: Path = field(default_factory=lambda: Path(os.getenv("OSS_V1_SKILLS_DIR", "./skills-osv1")))
    engine_url: str = field(default_factory=lambda: os.getenv("OSS_LOCAL_URL", "http://127.0.0.1:11400").rstrip("/"))
    engine_model: str = field(default_factory=lambda: os.getenv("OSS_LOCAL_MODEL", "qwen2.5-3b-q4_k_m"))
    engine_timeout: float = field(default_factory=lambda: env_float("OSS_LOCAL_TIMEOUT", 120.0))
    tier: str = field(default_factory=lambda: os.getenv("OSS_V1_TIER", "").strip().lower() or detect_tier().key)
    context_tokens: int = field(default_factory=lambda: env_int("OSS_V1_CONTEXT_TOKENS", 0))
    require_approval: bool = field(default_factory=lambda: env_bool("OSS_V1_REQUIRE_APPROVAL", True))
    allow_irreversible: bool = field(default_factory=lambda: env_bool("OSS_V1_ALLOW_IRREVERSIBLE", False))
    network_enabled: bool = field(default_factory=lambda: env_bool("OSS_V1_NETWORK", False))
    max_file_bytes: int = field(default_factory=lambda: env_int("OSS_V1_MAX_FILE_BYTES", 10_485_760))
    max_output_bytes: int = field(default_factory=lambda: env_int("OSS_V1_MAX_OUTPUT_BYTES", 65_536))
    som_abstain_threshold: float = field(default_factory=lambda: env_float("OSS_V1_SOM_ABSTAIN", 0.6))
    laya_model: str = field(default_factory=lambda: os.getenv("OSS_V1_LAYA_MODEL", ""))
    api_host: str = field(default_factory=lambda: os.getenv("OSS_V1_API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: env_int("OSS_V1_API_PORT", 8080))
    verifier_seed: int = field(default_factory=lambda: env_int("OSS_V1_VERIFIER_SEED", 20261021))
    kill_switch_file: Path = field(
        default_factory=lambda: Path(os.getenv("OSS_V1_KILL_SWITCH", "./data-osv1/kill.switch"))
    )
    audit_log: Path = field(default_factory=lambda: Path(os.getenv("OSS_V1_AUDIT_LOG", "./data-osv1/audit.log")))

    @classmethod
    def load(cls) -> Settings:
        settings = cls()
        if not settings.context_tokens:
            settings.context_tokens = DEVICE_TIERS[settings.tier].context_tokens
        # The inference timeout follows the tier's hardware, unless the
        # operator set OSS_LOCAL_TIMEOUT — an explicit setting is theirs and
        # is never overwritten. `engine_timeout` was defined but never used
        # before this; wiring it here is what makes it a setting at all.
        if not os.getenv("OSS_LOCAL_TIMEOUT"):
            settings.engine_timeout = DEVICE_TIERS[settings.tier].inference_timeout_s
        # The audit log and the kill switch live with the rest of the data.
        # They were fixed relative paths, so pointing OSS_V1_DATA_DIR
        # elsewhere moved the memory and the permissions while the audit
        # trail and the stop file stayed behind in the working directory —
        # the state an operator most needs to find, in the place they would
        # never look. An explicit override still wins.
        if not os.getenv("OSS_V1_AUDIT_LOG"):
            settings.audit_log = settings.data_dir / "audit.log"
        if not os.getenv("OSS_V1_KILL_SWITCH"):
            settings.kill_switch_file = settings.data_dir / "kill.switch"
        return settings

    # ── Derived paths ─────────────────────────────────────────────

    @property
    def db_path(self) -> Path:
        return self.data_dir / "osv1.db"

    @property
    def memory_db_path(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def audit_db_path(self) -> Path:
        return self.data_dir / "audit.db"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.workspace_dir, self.skills_dir, self.state_dir):
            path.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict[str, object]:
        tier = DEVICE_TIERS.get(self.tier, DEVICE_TIERS["lite"])
        return {
            "product": PRODUCT,
            "model": MODEL_NAME,
            "version": VERSION,
            "tier": tier.key,
            "tier_label": tier.label,
            "context_tokens": self.context_tokens,
            "min_ram_gb": tier.min_ram_gb,
            "vram_gb": tier.vram_gb,
            "engine_url": self.engine_url,
            "engine_model": self.engine_model,
            "require_approval": self.require_approval,
            "network_enabled": self.network_enabled,
            "data_dir": str(self.data_dir),
            "workspace_dir": str(self.workspace_dir),
        }
