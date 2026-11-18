"""keep_alive.py — watchdog for the two OSS Work services.
After the 5 Nov reboot this machine kills subprocesses randomly (system
error 0xC0000142 territory). Instead of hoping they survive, babysit them:
every 15s check both, restart whatever died, log everything.

Run: python keep_alive.py  (window minimized)
Stop: close the window or kill the process.
"""
import os
import subprocess
import sys
import time
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


def start_build_server():
    """15 Nov live: the machine silently killed the finished build's server
    while the user was about to try it. The build server (8080, newest
    workspace that has a server.py) is now a guarded citizen too.
    18 Nov live: the newest workspace's server.py was polluted with U+200C
    (SyntaxError), so the guard relaunched a broken file every 34 s and the
    port stayed dead. A candidate must COMPILE before it is launched; the
    guard then falls back to the next-newest valid workspace."""
    log("BUILD-SERVER(8080) down -> restart newest VALID workspace server.py")
    root = Path(os.environ.get("APPDATA", "")) / "osv_agent_ws"
    if not root.exists():
        return
    cands = sorted((d for d in root.iterdir() if (d / "server.py").exists()),
                   key=lambda d: d.stat().st_mtime, reverse=True)
    if not cands:
        log("  no workspace with server.py found")
        return
    # a workspace that fails to bring the port up twice is skipped for now,
    # so one broken build cannot mask a working one forever (18 Nov live).
    ws = next((d for d in cands
               if _compiles(d / "server.py") and _BUILD_FAIL.get(d.name, 0) < 2),
              None)
    if ws is None:
        log(f"  no usable server.py among {len(cands)} candidates (compile/fail budget)")
        return
    _BUILD_FAIL[ws.name] = _BUILD_FAIL.get(ws.name, 0) + 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    so = open(ws / "server_out.log", "a", encoding="utf-8", errors="replace")  # noqa: SIM115 — handle lives as long as the server process
    se = open(ws / "server_err.log", "a", encoding="utf-8", errors="replace")  # noqa: SIM115 — same
    subprocess.Popen([sys.executable, "server.py"], cwd=str(ws), env=env,
                     stdout=so, stderr=se,
                     creationflags=subprocess.CREATE_NO_WINDOW |
                     subprocess.DETACHED_PROCESS, close_fds=False)
    log(f"  launched server.py in {ws.name}")


def _compiles(path: Path) -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                           capture_output=True, timeout=25, check=False)
        return r.returncode == 0
    except Exception:  # noqa: BLE001 — a probe must never kill the guard
        return False


def main():
    log("keep_alive watchdog started")
    engine_grace = 0
    while True:
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
        time.sleep(15)


if __name__ == "__main__":
    main()
