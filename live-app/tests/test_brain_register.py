"""The 10 Nov merged-brain tests — user's REA+Craft plan (Rev 1.1):

DeepSeek + Moonshot Kimi are registered as cloud providers so the gateway's
task-aware bandit routes code builds to the smartest brains first.
Evidence dates are pinned so a future model rename fails loudly instead of
silently shipping a dead model id (the K2/K3 retirement is realtime).
"""
import random

import pytest

import oss_work_live as m
import osv_gateway as gw

# ---------------------------------------------------------------------------
# Static evidence: the provider registry carries the merged brain entries
# ---------------------------------------------------------------------------

def test_kimi_registry_entry_matches_official_docs():
    k = m.CLOUD_PROVIDERS["kimi"]
    assert k["url"] == "https://api.moonshot.ai/v1/chat/completions"
    assert k["default_model"].startswith("kimi-k3")   # K2 retired Dec 2026
    assert "platform.kimi.ai" in k["key_url"]


def test_deepseek_default_model_is_the_current_generation():
    d = m.CLOUD_PROVIDERS["deepseek"]
    # Dated evidence (.DeepSeek docs, 10 Nov): deepseek-flash is the cheap
    # current flagship with vision; deepseek-chat is a legacy alias.
    assert d["default_model"] == "deepseek-flash"
    assert "deepseek-v4-pro" in d["label"]   # hard-task upgrade documented


def test_providers_guide_exposes_both_brains():
    guide = m.providers_guide()
    names = [p["name"] for p in guide["providers"]]
    assert "kimi" in names and "deepseek" in names


# ---------------------------------------------------------------------------
# register_brain: encrypted upsert into the gateway pool (tmp DB)
# ---------------------------------------------------------------------------

@pytest.fixture()
def _gw_db(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "DB_PATH", tmp_path / "gateway.db")
    return tmp_path


def test_register_brain_upserts_with_encrypted_key(_gw_db):
    info = gw.register_brain("kimi", "sk-kimi-test-123")
    assert info["registered"] is True
    assert info["size_label"] == "Frontier"
    assert info["key_encrypted_len"] > 0
    assert info["key_decrypt_roundtrip"] is True
    assert info["model"] == "kimi-k3.1-pro"   # falls back to registry default


def test_register_brain_renewed_key_replaces_not_ignores(_gw_db):
    gw.register_brain("deepseek", "sk-ds-OLD")
    gw.register_brain("deepseek", "sk-ds-NEW")
    con = gw._connect()
    try:
        blob = con.execute(
            "SELECT api_key_enc FROM providers WHERE name = 'deepseek'"
        ).fetchone()[0]
    finally:
        con.close()
    assert gw.decrypt_key(blob) == "sk-ds-NEW"


def test_register_brain_unknown_provider_honest_failure(_gw_db):
    with pytest.raises(KeyError):
        gw.register_brain("kimi-v9-does-not-exist", "sk")


# ---------------------------------------------------------------------------
# ordered_chain: task-aware strength routing
# ---------------------------------------------------------------------------

def test_ordered_chain_sends_code_builds_to_frontier_brains(_gw_db):
    gw.register_brain("kimi", "sk-kimi")
    gw.register_brain("deepseek", "sk-ds")
    gw.upsert_provider("gemini", m.CLOUD_PROVIDERS["gemini"]["url"],
                       key="sk-gem", size_label="Large", intelligence_rank=35)
    # Deterministic bandit randomness: reliability sampling pinned so the
    # tier difference (Frontier > Large) alone decides the order.
    monkey_beta = (lambda a, b: 0.5)
    orig = random.betavariate
    random.betavariate = monkey_beta          # ordered_chain imports random
    try:
        chain = gw.ordered_chain(task="code")
    finally:
        random.betavariate = orig
    providers = [c["provider"] for c in chain]
    assert providers[-1] == "gemini"          # free anchor stays the fallback
    assert providers[0] in ("kimi", "deepseek")   # strong brain leads


def test_chain_cfg_caries_registry_default_model(_gw_db):
    gw.register_brain("deepseek", "sk-ds")
    chain = gw.ordered_chain(task="code")
    assert chain and chain[0]["provider"] == "deepseek"
    assert chain[0]["model"] == "deepseek-flash"
    assert chain[0]["url"] == m.CLOUD_PROVIDERS["deepseek"]["url"]
