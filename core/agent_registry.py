"""
سجل الوكلاء وإدارة القدرات
يدعم:
- تسجيل الوكلاء الديناميكي
- اكتشاف القدرات
- تقييم الوكلاء
- إدارة دورة الحياة
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class AgentCapability:
    """قدرة الوكيل"""
    name: str
    description: str
    category: str
    enabled: bool = True
    requires_approval: bool = False
    simulation_only: bool = False
    max_instances: int = 1


@dataclass
class AgentInfo:
    """معلومات الوكيل"""
    agent_type: str
    name: str
    description: str | None = None
    capabilities: list[AgentCapability] = field(default_factory=list)
    version: str = "1.0.0"
    status: str = "ready"  # ready, busy, error, disabled
    last_used: str | None = None
    usage_count: int = 0
    error_count: int = 0


class AgentRegistry:
    """سجل مركزي للوكلاء"""

    def __init__(self) -> None:
        self.agents: dict[str, AgentInfo] = {}
        self._capability_map: dict[str, list[str]] = {}  # capability -> agent types

    def register(self, info: AgentInfo) -> None:
        self.agents[info.agent_type] = info
        for cap in info.capabilities:
            if cap.enabled:
                self._capability_map.setdefault(cap.name, []).append(info.agent_type)

    def get(self, agent_type: str) -> AgentInfo | None:
        return self.agents.get(agent_type)

    def list_all(self) -> list[AgentInfo]:
        return list(self.agents.values())

    def find_by_capability(self, capability_name: str) -> list[AgentInfo]:
        agent_types = self._capability_map.get(capability_name, [])
        return [self.agents.get(at) for at in agent_types if at in self.agents]

    def find_by_category(self, category: str) -> list[AgentInfo]:
        return [a for a in self.agents.values() if any(c.category == category for c in a.capabilities)]

    def update_status(self, agent_type: str, status: str) -> bool:
        agent = self.agents.get(agent_type)
        if agent:
            agent.status = status
            return True
        return False

    def record_usage(self, agent_type: str, success: bool) -> None:
        agent = self.agents.get(agent_type)
        if agent:
            agent.usage_count += 1
            agent.last_used = datetime.now(timezone.utc).isoformat()
            if not success:
                agent.error_count += 1

    def get_summary(self) -> dict[str, Any]:
        total = len(self.agents)
        ready = sum(1 for a in self.agents.values() if a.status == "ready")
        busy = sum(1 for a in self.agents.values() if a.status == "busy")
        error = sum(1 for a in self.agents.values() if a.status == "error")
        disabled = sum(1 for a in self.agents.values() if a.status == "disabled")

        total_capabilities = sum(len(a.capabilities) for a in self.agents.values())
        enabled_capabilities = sum(1 for a in self.agents.values() for c in a.capabilities if c.enabled)

        return {
            "total_agents": total,
            "ready": ready,
            "busy": busy,
            "error": error,
            "disabled": disabled,
            "total_capabilities": total_capabilities,
            "enabled_capabilities": enabled_capabilities,
            "agents": [
                {
                    "type": a.agent_type,
                    "name": a.name,
                    "status": a.status,
                    "capabilities": [c.name for c in a.capabilities],
                    "usage_count": a.usage_count,
                    "error_count": a.error_count,
                }
                for a in self.agents.values()
            ],
        }


class CapabilityRegistry:
    """سجل القدرات عالمي"""

    def __init__(self) -> None:
        self.capabilities: dict[str, AgentCapability] = {}

    def register(self, capability: AgentCapability) -> None:
        self.capabilities[capability.name] = capability

    def get(self, name: str) -> AgentCapability | None:
        return self.capabilities.get(name)

    def list_all(self) -> list[AgentCapability]:
        return list(self.capabilities.values())

    def get_by_category(self, category: str) -> list[AgentCapability]:
        return [c for c in self.capabilities.values() if c.category == category]

    def is_enabled(self, name: str) -> bool:
        cap = self.capabilities.get(name)
        return cap is not None and cap.enabled

    def requires_approval(self, name: str) -> bool:
        cap = self.capabilities.get(name)
        return cap is not None and cap.requires_approval

    def is_simulation_only(self, name: str) -> bool:
        cap = self.capabilities.get(name)
        return cap is not None and cap.simulation_only


# القدرات الافتراضية
DEFAULT_CAPABILITIES: list[AgentCapability] = [
    # تجربة الملفات
    AgentCapability("read_file", "قراءة محتوى الملف", "filesystem", True, False, False),
    AgentCapability("list_directory", "قائمة محتويات المجلد", "filesystem", True, False, False),
    AgentCapability("search_files", "البحث عن ملفات بنمط", "filesystem", True, False, False),
    AgentCapability("file_write", "كتابة محتوى الملف", "filesystem", True, True, False),
    AgentCapability("file_delete", "حذف الملف", "filesystem", True, True, False),
    AgentCapability("file_move", "نقل الملف", "filesystem", True, True, False),
    # تجربة الكود
    AgentCapability("code_generation", "توليد كود", "code", True, False, False),
    AgentCapability("code_review", "مراجعة الكود", "code", True, False, False),
    AgentCapability("refactoring", "إعادة الهيكلة", "code", True, False, False),
    AgentCapability("code_execute", "تنفيذ الكود", "code", False, True, True),
    # تجربة المتصفح
    AgentCapability("browser_control", "التحكم بالمتصفح", "browser", False, True, True),
    AgentCapability("scrape_simulation", "محاكاة القراءة", "browser", True, False, True),
    AgentCapability("form_preview", "معاينة النموذج", "browser", True, False, True),
    # التكاملات الخارجية
    AgentCapability("external_message", "رسائل خارجية", "integration", False, True, True),
    AgentCapability("receive_data", "استقبال بيانات", "integration", False, True, True),
    AgentCapability("sync_data", "مزامنة البيانات", "integration", False, True, True),
    AgentCapability("webhook_delivery", "تسليم webhook", "integration", False, True, True),
    # الذاكرة
    AgentCapability("memory_write", "كتابة في الذاكرة", "memory", True, True, False),
    AgentCapability("memory_read", "قراءة من الذاكرة", "memory", True, False, False),
    AgentCapability("memory_search", "بحث في الذاكرة", "memory", True, False, False),
    AgentCapability("memory_delete", "حذف من الذاكرة", "memory", True, True, False),
    # التعلم
    AgentCapability("local_statistics", "إحصاءات محلية", "learning", True, False, False),
    AgentCapability("pattern_summary", "ملخص الأنماط", "learning", True, False, False),
    AgentCapability("methodology_draft", "مسودة المنهجية", "learning", True, False, False),
    # الأمان
    AgentCapability("static_scan", "فحص ثابت", "security", True, False, False),
    AgentCapability("secret_pattern_scan", "فحص أنماط السرقة", "security", True, False, False),
    AgentCapability("policy_report", "تقرير السياسة", "security", True, False, False),
    # تهمة
    AgentCapability("task_decomposition", "تحليل المهمة", "orchestration", True, False, False),
    AgentCapability("bounded_delegation", "تفويض محدود", "orchestration", True, False, False),
    AgentCapability("result_synthesis", "توليف النتائج", "orchestration", True, False, False),
]


def create_default_registry() -> CapabilityRegistry:
    """إنشاء سجل القدرات الافتراضي"""
    registry = CapabilityRegistry()
    for cap in DEFAULT_CAPABILITIES:
        registry.register(cap)
    return registry


def create_default_agent_registry() -> AgentRegistry:
    """إنشاء سجل الوكلاء الافتراضي"""
    registry = AgentRegistry()

    # معلومات الوكلاء الافتراضية
    agents = [
        AgentInfo(
            agent_type="file",
            name="FileAgent",
            description="عمليات الملفات المقيدة بالجذر",
            capabilities=[
                AgentCapability("read_file", "قراءة الملف", "filesystem"),
                AgentCapability("list_directory", "قائمة المجلد", "filesystem"),
                AgentCapability("search_files", "بحث عن ملفات", "filesystem"),
                AgentCapability("file_write", "كتابة الملف", "filesystem", requires_approval=True),
                AgentCapability("file_delete", "حذف الملف", "filesystem", requires_approval=True),
                AgentCapability("file_move", "نقل الملف", "filesystem", requires_approval=True),
            ],
        ),
        AgentInfo(
            agent_type="code",
            name="CodeAgent",
            description="مراجعة وتوليد الكود بدون تنفيذ",
            capabilities=[
                AgentCapability("code_generation", "توليد الكود", "code"),
                AgentCapability("code_review", "مراجعة الكود", "code"),
                AgentCapability("refactoring", "إعادة الهيكلة", "code"),
                AgentCapability("code_execute", "تنفيذ الكود", "code", simulation_only=True),
            ],
        ),
        AgentInfo(
            agent_type="browser",
            name="BrowserAgent",
            description="محاكاة المتصفح بدون جلسات حقيقية",
            capabilities=[
                AgentCapability("browser_control", "التحكم بالمتصفح", "browser", simulation_only=True),
                AgentCapability("scrape_simulation", "محاكاة القراءة", "browser"),
                AgentCapability("form_preview", "معاينة النموذج", "browser"),
            ],
        ),
        AgentInfo(
            agent_type="security",
            name="SecurityAgent",
            description="فحص الأمان المحلي",
            capabilities=[
                AgentCapability("static_scan", "فحص ثابت", "security"),
                AgentCapability("secret_pattern_scan", "فحص أنماط سرية", "security"),
                AgentCapability("policy_report", "تقرير السياسة", "security"),
            ],
        ),
        AgentInfo(
            agent_type="integration",
            name="IntegrationAgent",
            description="محاكاة التكاملات الخارجية",
            capabilities=[
                AgentCapability("external_message", "رسائل خارجية", "integration", simulation_only=True),
                AgentCapability("receive_data", "استقبال بيانات", "integration", simulation_only=True),
                AgentCapability("sync_data", "مزامنة البيانات", "integration", simulation_only=True),
                AgentCapability("webhook_delivery", "تسليم webhook", "integration", simulation_only=True),
            ],
        ),
        AgentInfo(
            agent_type="memory",
            name="MemoryAgent",
            description="ذاكرة SQLite معزولة",
            capabilities=[
                AgentCapability("memory_write", "كتابة في الذاكرة", "memory", requires_approval=True),
                AgentCapability("memory_read", "قراءة من الذاكرة", "memory"),
                AgentCapability("memory_search", "بحث في الذاكرة", "memory"),
                AgentCapability("memory_delete", "حذف من الذاكرة", "memory", requires_approval=True),
            ],
        ),
        AgentInfo(
            agent_type="learning",
            name="LearningAgent",
            description="إحصاءات التعلم الموضعية",
            capabilities=[
                AgentCapability("local_statistics", "إحصاءات محلية", "learning"),
                AgentCapability("pattern_summary", "ملخص الأنماط", "learning"),
                AgentCapability("methodology_draft", "مسودة المنهجية", "learning"),
            ],
        ),
    ]

    for agent in agents:
        registry.register(agent)

    return registry


# مثال الاستخدام:
"""
from core.agent_registry import create_default_registry, create_default_agent_registry

# سجل القدرات
caps = create_default_registry()
print(f"Total capabilities: {len(caps.list_all())}")
print(f"Filesystem capabilities: {len(caps.get_by_category('filesystem'))}")

# سجل الوكلاء
agents = create_default_agent_registry()
print(f"Total agents: {len(agents.list_all())}")
print(f"Security agents: {agents.find_by_category('security')}")

# البحث عن وكلاء بقدرة معينة
file_agents = agents.find_by_capability('read_file')
print(f"Agents with read_file: {[a.agent_type for a in file_agents]}")

# تحديث الحالة
agents.update_status('file', 'busy')
print(f"File agent status: {agents.get('file').status}")

# إحصائيات
summary = agents.get_summary()
print(f"Summary: {summary}")
"""
