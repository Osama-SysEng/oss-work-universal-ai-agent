"""
موارد تعليمية مدمجة للوكلاء
يدعم:
- قواعد معرفية
- أنماط التعلم
- مستندات مرجعية
- استراتيجيات حل المشكلات
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KnowledgeRule:
    """قاعدة معرفية للوكيل"""
    id: str
    domain: str
    rule: str
    description: str
    priority: int = 0
    tags: list[str] = field(default_factory=list)

    def matches(self, query: str) -> bool:
        query_lower = query.lower()
        return self.domain.lower() in query_lower or any(tag in query_lower for tag in self.tags)


@dataclass
class LearningPattern:
    """نمط تعلم للوكيل"""
    name: str
    description: str
    steps: list[str]
    applicable_domains: list[str]
    estimated_effort: str = "medium"

    def is_applicable(self, domain: str) -> bool:
        return domain.lower() in [d.lower() for d in self.applicable_domains]


class KnowledgeBase:
    """قاعدة معرفية للوكلاء"""

    def __init__(self) -> None:
        self.rules: list[KnowledgeRule] = []
        self.patterns: list[LearningPattern] = []
        self.references: dict[str, str] = {}

    def add_rule(self, rule: KnowledgeRule) -> None:
        self.rules.append(rule)

    def add_pattern(self, pattern: LearningPattern) -> None:
        self.patterns.append(pattern)

    def add_reference(self, key: str, content: str) -> None:
        self.references[key] = content

    def search(self, query: str) -> list[KnowledgeRule]:
        return [r for r in self.rules if r.matches(query)]

    def get_patterns_for_domain(self, domain: str) -> list[LearningPattern]:
        return [p for p in self.patterns if p.is_applicable(domain)]

    def get_reference(self, key: str) -> str | None:
        return self.references.get(key)


# قواعد المعرفة الافتراضية
DEFAULT_RULES: list[KnowledgeRule] = [
    KnowledgeRule(
        id="security_code_review_001",
        domain="security",
        rule="Always check for exec/eval before approving code execution",
        description="코드 실행 전 exec/eval 패턴 체크는 필수",
        priority=10,
        tags=["security", "code", "execution"],
    ),
    KnowledgeRule(
        id="file_operation_approval_001",
        domain="file",
        rule="File mutations require explicit approval before execution",
        description="ملف التعديلات تحتاج موافقة صريحة",
        priority=8,
        tags=["file", "write", "delete", "move", "approval"],
    ),
    KnowledgeRule(
        id="external_action_simulation_001",
        domain="external",
        rule="External actions must be simulation-only in safe release",
        description="الإجراءات الخارجية محاكاة فقط",
        priority=9,
        tags=["external", "simulation", "safe", "release"],
    ),
    KnowledgeRule(
        id="task_decomposition_001",
        domain="task",
        rule="Complex tasks should be decomposed into subtasks with max 5 agents",
        description="المهام المعقدة تتقسم لـ 5 وكلاء أقصى",
        priority=7,
        tags=["task", "decomposition", "agents", "orchestration"],
    ),
    KnowledgeRule(
        id="memory_isolation_001",
        domain="memory",
        rule="Memory is per-user isolated with parameterized queries only",
        description="الذاكرة معزولة لكل مستخدم",
        priority=8,
        tags=["memory", "sqlite", "isolation", "security"],
    ),
    KnowledgeRule(
        id="telemetry_validation_001",
        domain="telemetry",
        rule="Telemetry events must be validated before batching",
        description="أحداث التيلميتري موجّهة قبل التجميع",
        priority=6,
        tags=["telemetry", "validation", "batching"],
    ),
]

DEFAULT_PATTERNS: list[LearningPattern] = [
    LearningPattern(
        name="Security Review Pattern",
        description="مراجعة الأمان النظامية للكود",
        steps=[
            "Identify entry points and data flow",
            "Check for dangerous functions (exec, eval, subprocess)",
            "Validate input sanitization",
            "Review authentication and authorization",
            "Check for secret exposure patterns",
            "Generate findings report",
        ],
        applicable_domains=["security", "code", "review"],
        estimated_effort="medium",
    ),
    LearningPattern(
        name="File Operation Pattern",
        description="إجراءات الملفات الآمنة",
        steps=[
            "Validate path is within allowed root",
            "Check file size against limits",
            "Require approval for mutations",
            "Log the operation for audit",
            "Execute with error handling",
        ],
        applicable_domains=["file", "filesystem", "operations"],
        estimated_effort="low",
    ),
    LearningPattern(
        name="Task Decomposition Pattern",
        description="تقسيم المهام المعقدة",
        steps=[
            "Analyze task requirements",
            "Identify subtask categories",
            "Assign agents based on capabilities",
            "Set up context for each agent",
            "Collect and synthesize results",
        ],
        applicable_domains=["task", "orchestration", "agents"],
        estimated_effort="medium",
    ),
    LearningPattern(
        name="External Integration Pattern",
        description="تكاملات خارجية آمنة",
        steps=[
            "Verify simulation-only mode is active",
            "Check policy for external action permissions",
            "Validate provider configuration",
            "Log for audit without executing",
            "Return simulated result",
        ],
        applicable_domains=["external", "integration", "api"],
        estimated_effort="low",
    ),
]

DEFAULT_REFERENCES = {
    "policy": """
Safety Policy Guidelines:
- Default deny all capabilities
- Require explicit approval for mutations
- External actions are simulation-only
- Code execution is disabled in safe release
- File operations confined to allowed root
- Audit every operation
""",
    "architecture": """
OSS-Work Architecture:
- Core: Python agents with typed contracts
- Policy: Default-deny safety model
- Audit: Structured logging with sensitive field filtering
- Memory: SQLite with parameterized queries
- Telemetry: Transport-agnostic batching
- Web: Next.js operator console (static until API connected)
""",
    "api": """
API Usage (when enabled):
- Use OSS_WORK_API_KEY for authentication
- All mutations require approval
- External actions remain simulation-only
- Rate limiting applies per endpoint
- Audit trail for all operations
""",
}


class BuiltInKnowledge:
    """معرفة مدمجة للوكلاء"""

    def __init__(self) -> None:
        self.kb = KnowledgeBase()
        for rule in DEFAULT_RULES:
            self.kb.add_rule(rule)
        for pattern in DEFAULT_PATTERNS:
            self.kb.add_pattern(pattern)
        for key, content in DEFAULT_REFERENCES.items():
            self.kb.add_reference(key, content)

    def search_rules(self, query: str) -> list[dict[str, Any]]:
        """البحث عن قواعد معرفية - ترجع dict للاختبارات"""
        return [
            {"id": r.id, "domain": r.domain, "rule": r.rule, "description": r.description, "tags": r.tags}
            for r in self.kb.search(query)
        ]

    def get_patterns(self, domain: str) -> list[dict[str, Any]]:
        """الحصول على أنماط التعلم - ترجع dict للاختبارات"""
        return [
            {
                "name": p.name,
                "description": p.description,
                "applicable_domains": p.applicable_domains,
                "estimated_effort": p.estimated_effort,
            }
            for p in self.kb.get_patterns_for_domain(domain)
        ]

    def get_reference(self, key: str) -> str | None:
        """الحصول على مرجع"""
        return self.kb.get_reference(key)

    def get_summary(self) -> dict[str, Any]:
        """ملخص قاعدة المعرفة"""
        return {
            "rules_count": len(self.kb.rules),
            "patterns_count": len(self.kb.patterns),
            "references_count": len(self.kb.references),
            "domains": list(set(r.domain for r in self.kb.rules)),
        }
