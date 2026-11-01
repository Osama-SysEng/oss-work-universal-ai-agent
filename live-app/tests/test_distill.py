# -*- coding: utf-8 -*-
"""Distill: trajectories as a ledger, recipes as owned growth, retrieval by
short Arabic roots — the seed of the self-strengthening OS model."""
import json

import pytest

import osv_distill as ds


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "_dir", lambda: tmp_path / "d")
    (tmp_path / "d").mkdir(exist_ok=True)


# ------------------------------------------------------------------ ledger

def test_trajectory_recorded_as_jsonl(tmp_path):
    assert ds.record_trajectory("ابنِ", True, ["write_file"], ["a.py"], "تم")
    lines = (tmp_path / "d" / "trajectories.jsonl").read_bytes().splitlines()
    doc = json.loads(lines[0].decode("utf-8"))
    assert doc["ok"] is True and doc["files"] == ["a.py"]


def test_trajectory_failure_recorded_honestly():
    ds.record_trajectory("مهمة فاشلة", False, ["bash"], [], "فشل X")
    stats = ds.stats()
    assert stats["trajectories"] == 1 and stats["successful"] == 0


# ------------------------------------------------------------------- roots

def test_short_roots_collapse_hamzas_and_strip_prefixes():
    assert ds._roots("أمن") == ds._roots("امن")            # both hamza forms
    assert "مراج" in ds._roots("ومراجعة الملفات")          # و attached prefix stripped
    assert "المل" not in ds._roots("افتح الملف")           # stopword-ish roots out


def test_recipes_for_matches_derived_forms():
    def gw(cfg, msgs, effort="low", timeout=60, max_tokens=600):
        return ['{"name": "تقارير", "trigger_keywords": ["تقرير", "اجتماع"], '
                '"steps": ["اجمع", "اكتب", "راجع"]}']

    ds.distill_from_run("اكتب تقريراً عن اجتماع الفريق", ["a.md", "b.md"],
                        CHAIN, gw)
    hits = ds.recipes_for("أريد تقريراً جديداً عن المبيعات")   # تقرير→تقري root
    assert len(hits) == 1 and hits[0]["name"] == "تقارير"
    assert ds.recipes_for("وصف طويل عن الطبخ لا علاقة له") == []


# ------------------------------------------------------------------ recipes

CHAIN = [{"provider": "p", "key": "k", "model": "m"}]


def test_distill_requires_two_files_minimum():
    assert ds.distill_from_run("مهمة", ["one.py"], CHAIN,
                               lambda *a, **k: []) is None


def test_distill_requires_a_chain():
    assert ds.distill_from_run("مهمة", ["a.py", "b.py"], [],
                               lambda *a, **k: []) is None


def test_distill_stores_valid_recipe(tmp_path):
    def gw(cfg, msgs, effort="low", timeout=60, max_tokens=600):
        return ['```json\n{"name": "وصفة التقارير", "trigger_keywords": '
                '["تقرير", "annual"], "steps": ["اجمع البيانات من ملفات '
                'المساحة", "اكتب تقريراً فيه الأرقام", "تحقق بإعادة القراءة"]}'
                '\n```']

    r = ds.distill_from_run("أنشئ تقرير سنوي من البيانات", ["r.md", "d.csv"],
                            CHAIN, gw)
    assert r is not None and r["name"] == "وصفة التقارير"
    assert len(r["steps"]) == 3 and r["roots"]
    stored = json.loads((tmp_path / "d" / "recipes.json").read_text(
        encoding="utf-8"))
    assert len(stored) == 1


def test_distill_bad_json_is_honest_none():
    def gw(cfg, msgs, effort="low", timeout=60, max_tokens=600):
        return ["أجيب بنص بلا json إطلاقاً"]

    assert ds.distill_from_run("مهمة بعيدة", ["a.py", "b.py"], CHAIN,
                               gw) is None
    assert ds.stats()["recipes"] == 0


def test_distill_dedupes_same_name():
    def gw(cfg, msgs, effort="low", timeout=60, max_tokens=600):
        return ['{"name": "وصفة واحدة", "trigger_keywords": ["x"], '
                '"steps": ["أ", "ب"]}']

    ds.distill_from_run("مهمة أولى", ["a.py", "b.py"], CHAIN, gw)
    assert ds.distill_from_run("مهمة ثانية", ["a.py", "b.py"], CHAIN,
                               gw) is None
    assert ds.stats()["recipes"] == 1


# ---------------------------------------------------------------- retrieval

def test_recipes_for_matches_short_roots():
    def gw(cfg, msgs, effort="low", timeout=60, max_tokens=600):
        return ['{"name": "تقارير", "trigger_keywords": ["تقرير", "اجتماع"], '
                '"steps": ["اجمع", "اكتب", "راجع"]}']

    ds.distill_from_run("اكتب تقريراً عن اجتماع الفريق", ["a.md", "b.md"],
                        CHAIN, gw)
    hits = ds.recipes_for("أريد تقريراً جديداً عن المبيعات")   # تقرير→تقرير root
    assert len(hits) == 1 and hits[0]["name"] == "تقارير"
    assert ds.recipes_for("وصف طويل عن الطبخ لا علاقة له") == []


def test_inject_composes_block_and_empty_is_empty():
    assert ds.inject([]) == ""
    block = ds.inject([{"name": "وصفة", "steps": ["واحدة", "ثنائيتان"]}])
    assert "وصفة" in block and "1) واحدة" in block
