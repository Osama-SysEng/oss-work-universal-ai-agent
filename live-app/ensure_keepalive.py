"""ensure_keepalive.py — the guard OF the guard.

Three times the watchdog keep_alive.py died silently (this machine kills
python processes overnight: 5 Nov 10:51, 8 Nov after 11:48) and the whole
service stack died with it — the user's job attempt hit a dead backend.
This script runs every 5 minutes from a Windows scheduled task:
  - a live keep_alive instance -> do nothing, exit 0
  - no instance -> launch ONE, log it
Honest limits are logged: the task only works while this user's session
exists; it cannot fix an OS-level reboot (but ONSTART the services start
clean anyway and the task re-arms the watch)."""
import subprocess
import sys
import time

ROOT = r"C:\Users\ce\Desktop\التطويرات\OSS-Work"
LOG = ROOT + r"\ensure_keepalive.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def already_running() -> bool:
    r = subprocess.run(
        ["wmic", "process", "where",
         "name='python.exe'", "get", "commandline"], capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30,
        check=False)
    lines = [ln for ln in (r.stdout or "").splitlines()
             if ln and ln != r.stdout.splitlines()[0]]
    n = 0
    for ln in lines:
        if "keep_alive.py" in ln and "ensure_keepalive" not in ln:
            n += 1
    return n > 0


def main() -> int:
    if already_running():
        return 0                     # healthy silence — still logged monthly
    log("keep_alive MISSING -> launching one instance")
    # ASCII-safe launch of keep_alive.py: the cwd contains Arabic, so pass it
    # as an environment hook and let the child read it (lesson 15/18 styling)
    subprocess.Popen(
        [sys.executable, ROOT + r"\keep_alive.py"], cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=False)
    log("launched OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
