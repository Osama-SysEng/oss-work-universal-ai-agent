"""
اختبارات إضافية للميزات الجديدة
- Agent Registry
- Task Manager
- Knowledge Base
"""

import pytest

from pathlib import Path

from core.advanced import TaskManager, TaskPriority, TaskStatus
from core.agent_registry import (
    AgentCapability,
    AgentInfo,
    AgentRegistry,
    CapabilityRegistry,
    create_default_agent_registry,
    create_default_registry,
)


# =============================================================================
# Agent Registry Tests
# =============================================================================

def test_agent_registry_registration():
    registry = AgentRegistry()
    agent = AgentInfo(
        agent_type="test_agent",
        name="Test Agent",
        description="Test agent for registry",
        capabilities=[
            AgentCapability("test_cap", "Test capability", "test"),
        ],
    )
    registry.register(agent)

    assert registry.get("test_agent") is not None
    assert registry.get("test_agent").name == "Test Agent"
    assert len(registry.list_all()) == 1


def test_agent_registry_find_by_capability():
    registry = create_default_agent_registry()

    # البحث عن وكلاء بقدرة read_file
    file_agents = registry.find_by_capability("read_file")
    assert len(file_agents) >= 1
    agent_types = [a.agent_type for a in file_agents if a is not None]
    assert "file" in agent_types


def test_agent_registry_find_by_category():
    registry = create_default_agent_registry()

    security_agents = registry.find_by_category("security")
    assert len(security_agents) >= 1
    assert any(a.agent_type == "security" for a in security_agents if a)


def test_agent_registry_update_status():
    registry = create_default_agent_registry()

    assert registry.update_status("file", "busy")
    assert registry.get("file").status == "busy"

    assert not registry.update_status("nonexistent", "busy")


def test_agent_registry_record_usage():
    registry = create_default_agent_registry()

    registry.record_usage("file", True)
    agent = registry.get("file")
    assert agent.usage_count == 1
    assert agent.error_count == 0

    registry.record_usage("file", False)
    agent = registry.get("file")
    assert agent.usage_count == 2
    assert agent.error_count == 1


def test_agent_registry_summary():
    registry = create_default_agent_registry()
    summary = registry.get_summary()

    assert summary["total_agents"] >= 7  # الوكلاء الافتراضية
    assert "agents" in summary
    assert "total_capabilities" in summary


def test_capability_registry():
    registry = CapabilityRegistry()

    cap = AgentCapability("test_cap", "Test capability", "test")
    registry.register(cap)

    assert registry.get("test_cap") is not None
    assert registry.is_enabled("test_cap")
    assert not registry.requires_approval("test_cap")
    assert not registry.is_simulation_only("test_cap")

    # القدرات التي تتطلب موافقة
    write_cap = AgentCapability("file_write", "كتابة الملف", "filesystem", requires_approval=True)
    registry.register(write_cap)
    assert registry.requires_approval("file_write")
    # القدرات المحاكاة فقط
    exec_cap = AgentCapability("code_execute", "تنفيذ الكود", "code", simulation_only=True)
    registry.register(exec_cap)
    assert registry.is_simulation_only("code_execute")


def test_default_registries():
    cap_registry = create_default_registry()
    agent_registry = create_default_agent_registry()

    assert len(cap_registry.list_all()) >= 25  # القدرات الافتراضية
    assert len(agent_registry.list_all()) >= 7  # الوكلاء الافتراضية

    # التحقق من القدرات الأساسية
    assert cap_registry.is_enabled("read_file")
    assert cap_registry.is_enabled("code_review")
    assert cap_registry.is_enabled("static_scan")

    # التحقق من أن capability 평양 يعمل
    assert agent_registry.find_by_capability("read_file")[0].agent_type == "file"
    assert agent_registry.find_by_capability("code_execute")[0].agent_type == "code"
    assert agent_registry.find_by_capability("memory_write")[0].agent_type == "memory"


# =============================================================================
# Task Manager Tests
# =============================================================================

def test_task_manager_create_task():
    manager = TaskManager()
    task = manager.create_task("اختبار مهمة", priority=TaskPriority.HIGH)

    assert task.id is not None
    assert task.task == "اختبار مهمة"
    assert task.priority == TaskPriority.HIGH
    assert task.status == TaskStatus.PENDING


def test_task_manager_get_task():
    manager = TaskManager()
    task = manager.create_task("مهام اختبار")
    retrieved = manager.get_task(task.id)

    assert retrieved is not None
    assert retrieved.id == task.id
    assert retrieved.task == "مهام اختبار"


def test_task_manager_update_status():
    manager = TaskManager()
    task = manager.create_task("مهام حالة")

    assert manager.update_status(task.id, TaskStatus.IN_PROGRESS)
    assert task.status == TaskStatus.IN_PROGRESS

    assert not manager.update_status("nonexistent", TaskStatus.COMPLETED)


def test_task_manager_record_result():
    manager = TaskManager()
    task = manager.create_task("مهام نتيجة", agent="test_agent")

    manager.update_status(task.id, TaskStatus.IN_PROGRESS)
    manager.record_result(task.id, {"result": "success"})

    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"result": "success"}
    assert task.completed_at is not None


def test_task_manager_record_error():
    manager = TaskManager()
    task = manager.create_task("مهام خطأ", agent="test_agent")
    manager.update_status(task.id, TaskStatus.IN_PROGRESS)
    manager.record_result(task.id, {}, error="فشل الاختبار")

    assert task.status == TaskStatus.FAILED
    assert task.error == "فشل الاختبار"


def test_task_manager_get_pending_tasks():
    manager = TaskManager()
    manager.create_task("مهمة 1", priority=TaskPriority.HIGH)
    manager.create_task("مهمة 2", priority=TaskPriority.LOW)
    manager.create_task("مهمة 3", priority=TaskPriority.CRITICAL)

    # إكمال مهمة واحدة
    task = manager.get_task(manager.create_task("مهمة 4").id)
    task.status = TaskStatus.COMPLETED

    pending = manager.get_pending_tasks()
    assert len(pending) == 3

    # فلترة حسب الأولوية
    high_pending = manager.get_pending_tasks(priority=TaskPriority.HIGH)
    assert len(high_pending) == 1


def test_task_manager_get_agent_stats():
    manager = TaskManager()
    task = manager.create_task("مهام إحصائيات", agent="stats_agent")
    manager.update_status(task.id, TaskStatus.IN_PROGRESS)
    manager.record_result(task.id, {"data": "ok"})

    stats = manager.get_agent_stats("stats_agent")
    assert stats["tasks_completed"] == 1
    assert stats["tasks_failed"] == 0
    assert stats["success_rate"] > 0


def test_task_manager_get_summary():
    manager = TaskManager()
    manager.create_task("مهمة 1", priority=TaskPriority.HIGH)
    manager.create_task("مهمة 2")
    task = manager.create_task("مهمة 3", agent="agent1")
    manager.update_status(task.id, TaskStatus.COMPLETED)
    manager.record_result(task.id, {"done": True})

    summary = manager.get_summary()

    assert summary["total_tasks"] == 3
    assert summary["completed"] == 1
    assert summary["pending"] == 2
    assert summary["completion_rate"] == pytest.approx(33.33, abs=0.01)


def test_task_priorities_ordering():
    manager = TaskManager()

    # إنشاء مهام ب الأولويات مختلفة
    manager.create_task("منخفضة", priority=TaskPriority.LOW)
    manager.create_task("عالية", priority=TaskPriority.HIGH)
    manager.create_task("حرجة", priority=TaskPriority.CRITICAL)
    manager.create_task("متوسطة", priority=TaskPriority.MEDIUM)

    pending = manager.get_pending_tasks()

    # الترتيب: حرجة أولاً، ثم عالية، ثم متوسطة، ثم منخفضة
    assert pending[0].priority == TaskPriority.CRITICAL
    assert pending[1].priority == TaskPriority.HIGH
    assert pending[2].priority == TaskPriority.MEDIUM
    assert pending[3].priority == TaskPriority.LOW


# =============================================================================
# Knowledge Base Tests
# =============================================================================

def test_knowledge_base_search():
    from core.knowledge import BuiltInKnowledge

    kb = BuiltInKnowledge()
    rules = kb.search_rules("security")

    assert len(rules) >= 2  # قواعد الأمان
    assert any("security" in r["tags"] for r in rules)


def test_knowledge_base_patterns():
    from core.knowledge import BuiltInKnowledge

    kb = BuiltInKnowledge()
    patterns = kb.get_patterns("security")

    assert len(patterns) >= 1
    assert any(p["name"] == "Security Review Pattern" for p in patterns)


def test_knowledge_base_references():
    from core.knowledge import BuiltInKnowledge

    kb = BuiltInKnowledge()

    policy = kb.get_reference("policy")
    assert policy is not None
    assert "Safety Policy" in policy

    architecture = kb.get_reference("architecture")
    assert architecture is not None
    assert "Architecture" in architecture

    # مرجع غير موجود
    assert kb.get_reference("nonexistent") is None


def test_knowledge_base_summary():
    from core.knowledge import BuiltInKnowledge

    kb = BuiltInKnowledge()
    summary = kb.get_summary()

    assert summary["rules_count"] >= 6
    assert summary["patterns_count"] >= 4
    assert summary["references_count"] >= 3
    assert "security" in summary["domains"]
    assert "file" in summary["domains"]
    # domain "code" ليس موجودًا — القواعد المتعلقة بالكود لها domain "security"
    # تصحيح: نتحقق من وجود domain "telemetry" بدلاً من "code"
    assert "telemetry" in summary["domains"]
