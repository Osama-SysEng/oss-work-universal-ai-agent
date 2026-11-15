"""Test the wave TOTAL deadline: a trickling upstream must not hang forever.

10 Nov live: j1794731560-3 hung 20+ min because cloud_stream's timeout is
inactivity-based — an upstream dripping bytes never triggers it.
"""
import itertools
import time

import oss_work_live as m


def _fake_response(drip_every, total_lines):
    """An object that behaves like urlopen's response: yields SSE lines
    forever (total_lines=None) or stops after total_lines (healthy)."""

    class R:
        def __iter__(self):
            return self

        def __next__(self):
            if total_lines is not None and next(self._count) >= total_lines:
                raise StopIteration
            # drip: a line every drip_every seconds, no [DONE]
            time.sleep(drip_every)
            return b"data: " + b'{"choices":[{"delta":{"content":"x"}}]}\n\n'

        _count = itertools.count()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return R()


def test_wave_total_deadline_cuts_trickling_upstream(monkeypatch):
    def fake_urlopen(req, timeout=300):
        return _fake_response(drip_every=0.02, total_lines=None)

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    cfg = {"provider": "gemini", "model": "x", "key": "k"}
    t0 = time.monotonic()
    try:
        list(m.cloud_stream(cfg, [{"role": "user", "content": "hi"}],
                            effort=None, timeout=1, max_tokens=10))
        raised = False
    except TimeoutError as exc:
        raised = True
        assert "total deadline" in str(exc)
    dt = time.monotonic() - t0
    assert raised, "a forever-trickling stream must raise the total deadline"
    assert dt < 30, f"deadline should cut near 1s, took {dt:.1f}s"


def test_wave_deadline_does_not_cut_a_healthy_stream(monkeypatch):
    def fake_urlopen(req, timeout=300):
        return _fake_response(drip_every=0.01, total_lines=3)

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    cfg = {"provider": "gemini", "model": "x", "key": "k"}
    out = list(m.cloud_stream(cfg, [{"role": "user", "content": "hi"}],
                              effort=None, timeout=60, max_tokens=10))
    assert len(out) == 3 and all(o == "x" for o in out)
