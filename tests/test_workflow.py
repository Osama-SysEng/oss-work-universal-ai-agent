"""
اختبارات إضافية لسير العمل (Workflow)
"""

from core.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowStatus,
    StepStatus,
)


def test_workflow_creation():
    workflow = Workflow(id="test_wf", name="اختبار سير العمل")

    assert workflow.id == "test_wf"
    assert workflow.name == "اختبار سير العمل"
    assert workflow.status == WorkflowStatus.CREATED
    assert len(workflow.steps) == 0


def test_workflow_add_step():
    workflow = Workflow(id="test_wf", name="اختبار")
    step = WorkflowStep(id="step1", name="خطوة اختبار")

    workflow.add_step(step)

    assert len(workflow.steps) == 1
    assert workflow.steps[0].id == "step1"


def test_workflow_simple_execution():
    workflow = Workflow(id="test_wf", name="تنفيذ بسيط")

    step = WorkflowStep(
        id="step1",
        name="خطوة بسيطة",
        action=lambda: {"result": "success"},
    )
    workflow.add_step(step)

    result = workflow.execute()

    assert result["status"] == "completed"
    assert workflow.status == WorkflowStatus.COMPLETED
    assert len(result["results"]) == 1
    assert result["results"][0]["step"] == "step1"


def test_workflow_with_dependencies():
    workflow = Workflow(id="test_wf", name="تبعيات")

    step1 = WorkflowStep(
        id="step1",
        name="الخطوة الأولى",
        action=lambda: {"data": "from_step1"},
    )
    step2 = WorkflowStep(
        id="step2",
        name="الخطوة الثانية",
        depends_on=["step1"],
        action=lambda: {"data": "from_step2"},
    )
    step3 = WorkflowStep(
        id="step3",
        name="الخطوة الثالثة",
        depends_on=["step1", "step2"],
        action=lambda: {"data": "from_step3"},
    )

    workflow.add_step(step1)
    workflow.add_step(step2)
    workflow.add_step(step3)

    result = workflow.execute()

    assert result["status"] == "completed"
    assert workflow.status == WorkflowStatus.COMPLETED
    assert len(result["results"]) == 3


def test_workflow_step_failure():
    workflow = Workflow(id="test_wf", name="فشل")

    step1 = WorkflowStep(
        id="step1",
        name="خطوة ناجحة",
        action=lambda: {"ok": True},
    )
    step2 = WorkflowStep(
        id="step2",
        name="خطوة فاشلة",
        depends_on=["step1"],
        action=lambda: (_ for _ in ()).throw(Exception("خطأ مقصود")),
    )

    workflow.add_step(step1)
    workflow.add_step(step2)

    result = workflow.execute()

    assert result["status"] == "failed"
    assert workflow.status == WorkflowStatus.FAILED
    assert result["failed_step"] == "step2"


def test_workflow_get_status():
    workflow = Workflow(id="test_wf", name="حالة")

    step1 = WorkflowStep(id="step1", name="خطوة")
    workflow.add_step(step1)

    status = workflow.get_status()

    assert status["id"] == "test_wf"
    assert status["name"] == "حالة"
    assert status["status"] == WorkflowStatus.CREATED.value
    assert status["steps_count"] == 1


def test_workflow_cancel():
    workflow = Workflow(id="test_wf", name="إلغاء")

    step1 = WorkflowStep(id="step1", name="خطوة", status=StepStatus.RUNNING)
    workflow.add_step(step1)

    workflow.cancel()

    assert workflow.status == WorkflowStatus.CANCELLED
    assert step1.status == StepStatus.SKIPPED


def test_workflow_pending_steps():
    workflow = Workflow(id="test_wf", name="قائمة الانتظار")

    step1 = WorkflowStep(id="step1", name="خطوة 1")
    step2 = WorkflowStep(id="step2", name="خطوة 2", depends_on=["step1"])
    step3 = WorkflowStep(id="step3", name="خطوة 3")

    workflow.add_step(step1)
    workflow.add_step(step2)
    workflow.add_step(step3)

    pending = workflow.get_pending_steps()

    # step1 و step3 غير معتمدين على أي شيء
    assert len(pending) == 2
    assert pending[0].id == "step1"
    assert pending[1].id == "step3"


def test_workflow_completed_steps_not_pending():
    workflow = Workflow(id="test_wf", name="مكتمل")

    step1 = WorkflowStep(id="step1", name="خطوة 1")
    step1.status = StepStatus.COMPLETED
    step2 = WorkflowStep(id="step2", name="خطوة 2", depends_on=["step1"])
    step3 = WorkflowStep(id="step3", name="خطوة 3")

    workflow.add_step(step1)
    workflow.add_step(step2)
    workflow.add_step(step3)

    pending = workflow.get_pending_steps()

    # step2 تعتمد على step1 المكتمل
    assert len(pending) == 2
    assert pending[0].id == "step2"
    assert pending[1].id == "step3"


def test_workflow_already_completed():
    workflow = Workflow(id="test_wf", name="مكتمل")
    workflow.status = WorkflowStatus.COMPLETED

    result = workflow.execute()

    assert result["status"] == "error"
    assert "cannot be executed" in result["message"]


def test_workflow_metadata():
    workflow = Workflow(
        id="test_wf",
        name="معلومات إضافية",
        metadata={"owner": "test", "project": "oss-work"},
    )

    assert workflow.metadata["owner"] == "test"
    assert workflow.metadata["project"] == "oss-work"
