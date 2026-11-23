"""keep_alive.py — watchdog for the two OSS Work services.
After the 5 Nov reboot this machine kills subprocesses randomly (system
error 0xC0000142 territory). Instead of hoping they survive, babysit them:
every 15s check both, restart whatever died, log everything.

Run: python keep_alive.py  (window minimized)
Stop: close the window or kill the process.
"""
import faulthandler
import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\ce\Desktop\التطويرات\OSS-Work")
LOG = ROOT / "keepalive.log"
ENGINE_EXE = r"C:\tools\llama\llama-server.exe"
ENGINE_ARGS = ["-m", r"C:\tools\llama\models\qwen2.5-3b-q4_k_m.gguf",
               "--host", "127.0.0.1", "--port", "11400", "-c", "8192"]
# 10 Nov: FreeLLMAPI desktop (the 303-model brain router on 31415) dies with
# the same silent-kill disease — it is now a guarded citizen too.
ROUTER_EXE = (r"C:\Users\ce\AppData\Local\Programs\freellmapi-desktop"
              r"\FreeLLMAPI.exe")
ROUTER_CWD = r"C:\Users\ce\AppData\Local\Programs\freellmapi-desktop"
_BUILD_FAIL: dict[str, int] = {}     # workspace -> failed launches since port was up


def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except urllib.error.HTTPError:
        return True                     # an HTTP error answer = process alive
    except Exception:                   # noqa: BLE001
        return False


def start_engine():
    log("ENGINE down -> restart")
    subprocess.Popen([ENGINE_EXE, *ENGINE_ARGS],
                     creationflags=subprocess.CREATE_NO_WINDOW)


def start_backend():
    log("BACKEND down -> restart")
    out = open(ROOT / "backend_out.log", "a", encoding="utf-8", errors="replace")  # noqa: SIM115 — handle lives as long as the backend process
    err = open(ROOT / "backend_err.log", "a", encoding="utf-8", errors="replace")  # noqa: SIM115 — same
    # 15 Nov live: without PYTHONIOENCODING the revived backend died on the
    # emoji banner print (cp1252) — every watchdog revive was a guaranteed
    # crash. The revive env must match the manual-start ritual.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    subprocess.Popen(["python", "oss_work_live.py"], cwd=str(ROOT),
                     stdout=out, stderr=err, env=env,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                     close_fds=False)


def start_router():
    log("ROUTER(31415) down -> restart FreeLLMAPI desktop")
    subprocess.Popen([ROUTER_EXE], cwd=ROUTER_CWD,
                     creationflags=subprocess.DETACHED_PROCESS)


def _port_up() -> bool:
    return alive("http://127.0.0.1:8080/")


def start_build_server():
    """15 Nov live: the machine silently killed the finished build's server
    while the user was about to try it. The build server (8080, newest
    workspace that has a server.py) is now a guarded citizen too.
    18 Nov live: the newest workspace's server.py was polluted with U+200C
    (SyntaxError) and a later one was truncated (exit 0, no serve loop), so
    relaunching by mtime alone kept the port dead. The guard now PROVES a
    candidate: launch, wait up to 6 s for the port, else kill and try the
    next-newest compiling workspace.
    23 Nov live: a candidate server.py defaulted to PORT 8000 and BOUND THE
    BACKEND PORT — the watchdog then "revived" the backend with a foreign
    demo app. A candidate must never steal 8000; the launch is aborted the
    moment api/health stops answering."""
    log("BUILD-SERVER(8080) down -> proving candidates one by one")
    root = Path(os.environ.get("APPDATA", "")) / "osv_agent_ws"
    if not root.exists():
        return
    cands = sorted((d for d in root.iterdir() if (d / "server.py").exists()),
                   key=lambda d: d.stat().st_mtime, reverse=True)
    if not cands:
        log("  no workspace with server.py found")
        return
    for ws in cands:
        if _BUILD_FAIL.get(ws.name, 0) >= 2:
            continue
        if not _compiles(ws / "server.py"):
            log(f"  {ws.name}: server.py does not compile — skip")
            _BUILD_FAIL[ws.name] = 2
            continue
        try:
            src = (ws / "server.py").read_text(encoding="utf-8", errors="ignore")
        except OSError:
            src = ""
        if "8080" not in src:
            # a hardcoded 8000 (or any foreign port) would bind the WRONG port
            log(f"  {ws.name}: server.py hardcodes no 8080 — not a build-server candidate")
            _BUILD_FAIL[ws.name] = 2
            continue
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        so = open(ws / "server_out.log", "a", encoding="utf-8", errors="replace")  # noqa: SIM115 — handle lives as long as the server process
        se = open(ws / "server_err.log", "a", encoding="utf-8", errors="replace")  # noqa: SIM115 — same
        proc = subprocess.Popen([sys.executable, "server.py"], cwd=str(ws), env=env,
                                stdout=so, stderr=se,
                                creationflags=subprocess.CREATE_NO_WINDOW |
                                subprocess.DETACHED_PROCESS, close_fds=False)
        for _ in range(6):
            time.sleep(1)
            if not alive("http://127.0.0.1:8000/api/health"):
                log(f"  {ws.name}: stole port 8000 — killed, marking failed")
                _BUILD_FAIL[ws.name] = 2
                try:
                    proc.terminate()
                except Exception as exc:  # noqa: BLE001
                    log(f"  terminate {ws.name} skipped: {type(exc).__name__}")
                break
            if _port_up():
                log(f"  UP: {ws.name} (8080 answering)")
                _BUILD_FAIL.pop(ws.name, None)
                return
        else:
            log(f"  {ws.name}: launched but 8080 never answered — next candidate")
            _BUILD_FAIL[ws.name] = _BUILD_FAIL.get(ws.name, 0) + 1
            try:
                proc.terminate()
            except Exception as exc:  # noqa: BLE001 — cleanup must never kill the guard
                log(f"  terminate {ws.name} skipped: {type(exc).__name__}")
    log("  no candidate brought 8080 up this cycle")


def _compiles(path: Path) -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                           capture_output=True, timeout=25, check=False)
        return r.returncode == 0
    except Exception:  # noqa: BLE001 — a probe must never kill the guard
        return False


def main():
    # 18 Nov live: the watchdog proved 8080 then vanished without a trace —
    # no CYCLE ERROR, no frozen cycle. pythonw has no console, so a hard fault
    # is invisible. faulthandler + an explicit heartbeat make silence readable.
    fault = (ROOT / "watchdog_fault.log").open("a", encoding="utf-8")
    faulthandler.enable(file=fault, all_threads=True)
    log("keep_alive watchdog started")
    engine_grace = 0
    ticks = 0
    while True:
        try:
            engine_grace = _cycle(engine_grace)
        except Exception:  # noqa: BLE001 — one bad cycle must not kill the guard
            log("CYCLE ERROR " + " | ".join(
                traceback.format_exc().splitlines()[-2:])[:400])
        ticks += 1
        if ticks % 4 == 0:
            log(f"heartbeat: 8080 {'up' if alive('http://127.0.0.1:8080/') else 'down'}, "
                f"8000 {'up' if alive('http://127.0.0.1:8000/api/health') else 'down'}")
        time.sleep(15)


def _cycle(engine_grace: int) -> int:
    if not alive("http://127.0.0.1:11400/health"):
        if engine_grace == 0:
            start_engine()
            engine_grace = 6          # model takes ~60-90s to load
        else:
            engine_grace -= 1
    else:
        engine_grace = 0
    if not alive("http://127.0.0.1:8000/api/health"):
        start_backend()
        time.sleep(10)                # give uvicorn time to bind
        # 23 Nov live: while 8000 is broken, a workspace candidate launched for
        # 8080 can BIND 8000 (its server.py defaults there) and masquerade as
        # the backend. Never probe build candidates in the same cycle as a
        # backend revive; wait until api/health answers again.
        return engine_grace
    if not alive("http://127.0.0.1:31415/v1/models"):
        router_grace = getattr(main, "_router_grace", 0)
        if router_grace == 0:
            start_router()
            main._router_grace = 2    # electron app takes ~30s to bind
        else:
            main._router_grace = router_grace - 1
    else:
        main._router_grace = 0
    if not alive("http://127.0.0.1:8080/"):
        build_grace = getattr(main, "_build_grace", 0)
        if build_grace == 0:
            start_build_server()
            main._build_grace = 1     # one retry cycle before again
        else:
            main._build_grace = build_grace - 1
    else:
        main._build_grace = 0
        _BUILD_FAIL.clear()           # a live port forgives past failures
    return engine_grace


if __name__ == "__main__":
    main()
