"""keep_alive.py — watchdog for the two OSS Work services.
After the 5 Nov reboot this machine kills subprocesses randomly (system
error 0xC0000142 territory). Instead of hoping they survive, babysit them:
every 15s check both, restart whatever died, log everything.

Run: python keep_alive.py  (window minimized)
Stop: close the window or kill the process.
"""
import subprocess
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
    subprocess.Popen(["python", "oss_work_live.py"], cwd=str(ROOT),
                     stdout=out, stderr=err,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                     close_fds=False)


def start_router():
    log("ROUTER(31415) down -> restart FreeLLMAPI desktop")
    subprocess.Popen([ROUTER_EXE], cwd=ROUTER_CWD,
                     creationflags=subprocess.DETACHED_PROCESS)


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
        time.sleep(15)


if __name__ == "__main__":
    main()
