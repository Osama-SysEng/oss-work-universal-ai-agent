"""Launch OSS Work: backend + frontend + open browser."""
import subprocess
import time
import sys

print("Starting OSS Work stack...\n")

# 1. Start backend
print("[1/3] Starting backend on :8000...")
backend = subprocess.Popen(
    [sys.executable, "oss_work_api.py"],
    cwd=r"C:\Users\ce\Desktop\التطويرات\OSS-Work",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(3)

# 2. Start frontend
print("[2/3] Starting frontend on :3000...")
frontend = subprocess.Popen(
    [sys.executable, "-m", "npm", "run", "dev", "--", "--host", "0.0.0.0"],
    cwd=r"C:\Users\ce\Desktop\التطويرات\OSS-Work",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(4)

# 3. Open browser
print("[3/3] Opening browser...")
import webbrowser
webbrowser.open("http://localhost:3000")

print("\n✅ OSS Work is running!")
print("   Frontend: http://localhost:3000")
print("   API:      http://127.0.0.1:8000/api/info")
print("\nPress Ctrl+C to stop both servers.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    backend.terminate()
    frontend.terminate()
