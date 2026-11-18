"""18 Nov live: generated media must land where the built product can read it.

The wrappers pass ctx.workspace/"media" so an index.html can embed the asset
by relative path. These tests pin the base-directory plumbing without network.
"""

from pathlib import Path

import osv_media
import osv_motion


def test_media_dir_honours_base(tmp_path):
    d = osv_media.media_dir(tmp_path / "media")
    assert d == tmp_path / "media"
    assert d.is_dir()


def test_motion_dir_honours_base(tmp_path):
    d = osv_motion.motion_dir(tmp_path / "media")
    assert d == tmp_path / "media"
    assert d.is_dir()


def test_wrappers_accept_out_base_kwarg():
    import inspect

    assert "out_base" in inspect.signature(osv_media.MediaKit.generate_image).parameters
    assert "out_base" in inspect.signature(osv_media.MediaKit.generate_video).parameters
    assert "out_base" in inspect.signature(osv_motion.motion_clip).parameters
    assert "out_base" in inspect.signature(osv_motion.genjutsu_variants).parameters
    assert "out_base" in inspect.signature(osv_motion.compose_cinema).parameters


def test_motion_dir_default_is_app_media():
    assert Path(osv_motion.motion_dir()).name == "media"
