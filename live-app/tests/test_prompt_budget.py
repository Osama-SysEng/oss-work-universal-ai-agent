"""The prompt budget is a CAPABILITY, not cosmetics.

Measured 22 Nov: after the tool layer grew to 37 tools, the system prompt hit
11,346 chars (~3.8K tokens) before the local 8192-token engine did any work —
half its window spent on a catalog. Two-tier docs (full for hot tools, compact
one-liners otherwise) brought it to 9,353 and still lets a media task expand
its own tools. These tests pin both halves.
"""
import osv_agent as ag


def _runtime_table():
    import osv_clean
    import osv_edit
    import osv_git
    import osv_longio
    import osv_mcp
    import osv_media as md
    import osv_sec
    import osv_team as tm

    table = dict(ag.TOOLS)
    for part in (md.media_tools(md.MediaKit()), osv_clean.clean_tools(None),
                 osv_sec.sec_tools(), osv_mcp.mcp_tools(),
                 osv_git.git_tools(), osv_longio.longio_tools(),
                 osv_edit.edit_tools(), tm.team_tool()):
        table.update(part)
    return table


def test_runtime_prompt_fits_a_code_task_budget():
    table = _runtime_table()
    msg = ag.compose_system("أصلح خطأ في ملف بايثون وأعد الاختبار", table, "")
    # 9,353 measured; hard cap keeps future tool growth from silently eating
    # the local engine's window (8192 tokens ≈ 20K chars realistic).
    assert len(msg) < 10_000, f"system prompt grew to {len(msg)} chars"
    for core in ("edit_file", "apply_patch", "verify_project", "bash"):
        assert core in msg


def test_media_task_expands_media_tool_docs():
    table = _runtime_table()
    code = ag.compose_system("أصلح بايثون", table, "")
    media = ag.compose_system("اصنع صورة شعار لفيديو متحرك", table, "")
    # the media tools were present before, but compacted; the media task must
    # recover their FULL argument signatures (they have 5-8 args).
    assert len(media) > len(code)
    assert "image_generate" in media and "video_generate" in media
    assert "motion_generate" in media


def test_compact_docs_still_show_every_tool_name():
    table = _runtime_table()
    msg = ag.compose_system("أصلح بايثون", table, "")
    for name in table:
        assert f"- {name}" in msg, f"{name} vanished from the catalog"
