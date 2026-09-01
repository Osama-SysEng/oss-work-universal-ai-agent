"""Safe OSS-Work runtime entrypoint."""
from __future__ import annotations

import json
from typing import Any

from core.agents.orchestrator import OrchestratorAgent
from core.config import PROJECT_NAME, VERSION, ensure_runtime_dirs


def run(task: str, *, user_id: str = "local", context: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_runtime_dirs()
    merged = dict(context or {})
    merged["user_id"] = user_id
    return OrchestratorAgent(task=task, context=merged).execute()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=f"{PROJECT_NAME} safe local CLI")
    parser.add_argument("task", nargs="?", default="status")
    parser.add_argument("--user", default="local")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(f"{PROJECT_NAME} {VERSION}")
        return
    print(json.dumps(run(args.task, user_id=args.user), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
