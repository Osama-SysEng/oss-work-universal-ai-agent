from pathlib import Path

from core.agents.code_agent import CodeAgent
from core.agents.file_agent import FileAgent
from core.policy import Decision, SafetyPolicy
from scripts.updater import SkillDownloader, Updater


def test_mutation_requires_approval():
    decision = SafetyPolicy().evaluate("file_write")
    assert decision.decision is Decision.REQUIRES_APPROVAL


def test_file_agent_cannot_escape_root(tmp_path: Path):
    result = FileAgent(context={"task": "read", "path": str(tmp_path.parent / "outside.txt"), "allowed_root": str(tmp_path)}).execute()
    assert result["status"] == "failed"
    assert "outside" in result["errors"][0]


def test_file_write_requires_approval(tmp_path: Path):
    result = FileAgent(context={"task": "write", "path": str(tmp_path / "x.txt"), "content": "x", "allowed_root": str(tmp_path)}).execute()
    assert result["status"] == "denied"
    assert not (tmp_path / "x.txt").exists()


def test_code_execution_is_denied():
    result = CodeAgent(context={"task": "execute", "code": "print('unsafe')"}).execute()
    assert result["status"] == "denied"
    assert result["decision"]["external_action_attempted"] is False


def test_updater_never_installs(tmp_path: Path):
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"safe")
    digest = __import__("hashlib").sha256(b"safe").hexdigest()
    result = Updater().inspect_artifact(artifact, digest)
    assert result["status"] == "review_required"
    assert result["install_attempted"] is False
    assert SkillDownloader().download_skill("anything")["install_attempted"] is False
