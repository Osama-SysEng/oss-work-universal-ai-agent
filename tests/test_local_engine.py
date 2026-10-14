"""Tests for the local inference engine client (no server required)."""

import pytest

from core.services.local_engine import LocalEngine, LocalEngineError


def test_health_false_when_down():
    eng = LocalEngine(base_url="http://127.0.0.1:9")
    assert eng.health() is False


def test_chat_raises_helpful_error_when_down():
    eng = LocalEngine(base_url="http://127.0.0.1:9", timeout=2)
    with pytest.raises(LocalEngineError, match="llama-server"):
        eng.chat([{"role": "user", "content": "hi"}])


def test_defaults_from_env(monkeypatch):
    monkeypatch.setenv("OSS_LOCAL_URL", "http://127.0.0.1:9999/")
    monkeypatch.setenv("OSS_LOCAL_MODEL", "demo-model")
    eng = LocalEngine()
    assert eng.base_url == "http://127.0.0.1:9999"
    assert eng.model_label == "demo-model"
