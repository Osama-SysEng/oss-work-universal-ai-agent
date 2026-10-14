"""oss-os CLI: boot | status | run | tasks | submit | jobs | skills | serve."""

from __future__ import annotations

import argparse
import asyncio
import json

from ossys import config
from ossys.kernel import Kernel


def _print(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_boot(_args: argparse.Namespace) -> None:
    _print(Kernel().boot())


def cmd_status(_args: argparse.Namespace) -> None:
    _print(Kernel().status())


def cmd_run(args: argparse.Namespace) -> None:
    _print(Kernel().run(args.task, task_id=args.agent))


def cmd_tasks(args: argparse.Namespace) -> None:
    from ossys.task_registry import all_tasks, by_archetype, search

    if args.search:
        rows = search(args.search)
    elif args.archetype:
        rows = by_archetype(args.archetype)
    else:
        rows = all_tasks()
    _print([{"id": t.id, "archetype": t.archetype, "title": t.title} for t in rows])


def cmd_submit(args: argparse.Namespace) -> None:
    kernel = Kernel()
    _print(kernel.submit(args.task, delay_s=args.delay, interval_s=args.every, repeat=bool(args.every)))


def cmd_jobs(_args: argparse.Namespace) -> None:
    from ossys import store

    _print(store.list_jobs())


def cmd_drain(_args: argparse.Namespace) -> None:
    _print(Kernel().run_background_once())


def cmd_skill_new(args: argparse.Namespace) -> None:
    from ossys import skills

    _print(vars(skills.ask_interactive(args.name, args.purpose)))


def cmd_serve(args: argparse.Namespace) -> None:
    """Run the background loop until Ctrl+C (the OS staying on the job)."""
    from ossys import scheduler

    kernel = Kernel()
    kernel.boot()
    print(f"oss-work OS v{config.OS_VERSION} serving background jobs (Ctrl+C to stop).")
    try:
        asyncio.run(scheduler.loop_forever(lambda t: kernel.run(t), interval_s=args.interval))
    except KeyboardInterrupt:
        print("stopped.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oss-os", description="oss-work OS (local only).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("boot", help="Boot the OS (engine check + state init).")
    sub.add_parser("status", help="Show OS status.")

    run_p = sub.add_parser("run", help="Run a task now.")
    run_p.add_argument("task")
    run_p.add_argument("--agent", default=None, help="Task agent id T001..T300.")

    tasks_p = sub.add_parser("tasks", help="List the 300 task agents.")
    tasks_p.add_argument("--archetype", default=None)
    tasks_p.add_argument("--search", default=None)

    submit_p = sub.add_parser("submit", help="Submit background work.")
    submit_p.add_argument("task")
    submit_p.add_argument("--delay", type=float, default=0)
    submit_p.add_argument("--every", type=float, default=None, help="Repeat interval seconds.")

    sub.add_parser("jobs", help="List background jobs.")
    sub.add_parser("drain", help="Execute due background jobs once.")

    skill_p = sub.add_parser("skill-new", help="Build a skill via yes/no questions.")
    skill_p.add_argument("name")
    skill_p.add_argument("purpose")

    serve_p = sub.add_parser("serve", help="Serve background jobs until stopped.")
    serve_p.add_argument("--interval", type=float, default=5.0)
    return parser


_HANDLERS = {
    "boot": cmd_boot,
    "status": cmd_status,
    "run": cmd_run,
    "tasks": cmd_tasks,
    "submit": cmd_submit,
    "jobs": cmd_jobs,
    "drain": cmd_drain,
    "skill-new": cmd_skill_new,
    "serve": cmd_serve,
}


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
