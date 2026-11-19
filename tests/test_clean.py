"""18 Nov live: cleanup must be provably safe — temp-only, age-gated, dry-run first."""

import os
import time

import osv_clean


def _age(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_dry_run_never_deletes(tmp_path):
    f = tmp_path / "old.tmp"
    f.write_text("x", encoding="utf-8")
    _age(f, 30)
    ok, obs = osv_clean.apply(older_than_days=7, dry_run=True,
                              paths=[str(tmp_path)])
    assert ok and "سيُحذف" in obs and "dry_run" in obs
    assert f.exists()


def test_apply_deletes_only_old_junk_inside_temp(tmp_path):
    old_junk = tmp_path / "old.log"
    old_junk.write_text("x", encoding="utf-8")
    _age(old_junk, 30)
    fresh_junk = tmp_path / "fresh.log"
    fresh_junk.write_text("x", encoding="utf-8")
    keep = tmp_path / "notes.txt"
    keep.write_text("x", encoding="utf-8")
    _age(keep, 30)

    ok, obs = osv_clean.apply(older_than_days=7, dry_run=False,
                              paths=[str(tmp_path)])
    assert ok and "حُذف" in obs
    assert not old_junk.exists()
    assert fresh_junk.exists()
    assert keep.exists()


def test_apply_refuses_outside_temp():
    ok, obs = osv_clean.apply(older_than_days=0, dry_run=True,
                              paths=[r"C:\Users\ce\Desktop"])
    assert not ok and "مؤقتة فقط" in obs


def test_scan_reports_junk_and_suspicious(tmp_path):
    (tmp_path / "a.tmp").write_text("x", encoding="utf-8")
    (tmp_path / "dropper.exe").write_text("x", encoding="utf-8")
    (tmp_path / "invoice.pdf.exe").write_text("x", encoding="utf-8")
    ok, obs = osv_clean.scan([str(tmp_path)], min_age_days=0)
    assert ok
    assert "مرشّحات التنظيف" in obs
    assert "dropper.exe" in obs
    assert "امتداد مزدوج" in obs


def test_apply_is_gated_in_safe_mode():
    reg = osv_clean.clean_tools(kit=None)

    class Kit:
        yolo = False

    reg = osv_clean.clean_tools(kit=Kit())
    ok, obs = reg["cleanup_apply"]["fn"](None, dry_run=False)
    assert not ok and "أدوات كاملة" in obs


def test_apply_allowed_when_engine_yolo(tmp_path):
    import osv_device

    (tmp_path / "old.tmp").write_text("x", encoding="utf-8")
    os.utime(tmp_path / "old.tmp", (time.time() - 30 * 86400,) * 2)
    kit = osv_device.DeviceKit(yolo=True)
    reg = osv_clean.clean_tools(kit)
    ok, obs = reg["cleanup_apply"]["fn"](None, dry_run=False,
                                        older_than_days=7,
                                        paths=[str(tmp_path)])
    assert ok and "حُذف" in obs
    assert not (tmp_path / "old.tmp").exists()
