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
    out = open(ROOT / "backend_out.log", "a", encoding="utf-8", errors="replace")
    err = open(ROOT / "backend_err.log", "a", encoding="utf-8", errors="replace")
    subprocess.Popen(["python", "oss_work_live.py"], cwd=str(ROOT),
                     stdout=out, stderr=err,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                     close_fds=False)


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
        time.sleep(15)


if __name__ == "__main__":
    main()
