"""The command line for OS_V1.

Standard library only, so it runs on a fresh machine with nothing installed
beyond the core package. Every command prints what actually happened, and
says when something is unavailable instead of pretending.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from osv1.agents.registry import REGISTRY
from osv1.config import Settings
from osv1.runtime import OSRuntime

RUNTIME: OSRuntime | None = None


def runtime() -> OSRuntime:
    global RUNTIME
    if RUNTIME is None:
        RUNTIME = OSRuntime(settings=Settings.load())
    return RUNTIME


def _print(payload: Any) -> None:
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ── commands ───────────────────────────────────────────────


def cmd_plan(args: argparse.Namespace) -> int:
    result = runtime().plan(args.task, agent_id=args.agent or "")
    _print(result.as_dict())
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    result = runtime().build(args.task, agent_id=args.agent or "")
    _print(result.as_dict())
    return 0 if result.status in ("completed", "planned") else 1


def cmd_agents(args: argparse.Namespace) -> int:
    if args.search:
        found = REGISTRY.search(args.search, limit=args.limit)
        _print([{"id": agent.id, "title": agent.title, "score": score} for agent, score in found])
        return 0
    agents = list(REGISTRY.all())
    if args.domain:
        agents = REGISTRY.by_domain(args.domain)
    if args.specialization:
        agents = REGISTRY.by_specialization(args.specialization)
    agents = agents[: args.limit]
    _print(
        [
            {
                "id": agent.id,
                "title": agent.title,
                "domain": agent.domain.key,
                "specialization": agent.specialization.key,
                "capabilities": list(agent.capabilities),
                "risk": agent.risk,
            }
            for agent in agents
        ]
    )
    return 0


def cmd_agent(args: argparse.Namespace) -> int:
    agent = REGISTRY.get(args.agent_id)
    if agent is None:
        print(f"no agent {args.agent_id}", file=sys.stderr)
        return 1
    _print(agent.as_dict())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    _print(runtime().status())
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    store = runtime().memory
    if args.memory_action == "export":
        _print(store.export())
        return 0
    if args.memory_action == "delete":
        if args.entry_id is None:
            print("delete needs an entry id", file=sys.stderr)
            return 1
        _print({"deleted": store.delete(args.entry_id)})
        return 0
    entries = store.list(kind=args.kind or None, limit=args.limit)
    _print([entry.as_dict() for entry in entries])
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    log = runtime().audit
    if args.verify:
        _print(log.verify_chain())
        return 0
    _print(log.recent(args.limit))
    return 0


def cmd_grant(args: argparse.Namespace) -> int:
    grant = runtime().permissions.grant(args.scope, args.target, readonly=args.readonly)
    _print(grant.as_dict())
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    removed = runtime().permissions.revoke(args.scope, args.target or None)
    _print({"removed": removed})
    return 0


def cmd_approvals(args: argparse.Namespace) -> int:
    store = runtime().approvals
    if args.approval_id:
        request = store.decide(args.approval_id, approve=not args.reject)
        if request is None:
            print(f"no approval {args.approval_id}", file=sys.stderr)
            return 1
        _print(request.as_dict())
        return 0
    _print([request.as_dict() for request in store.pending()])
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    switch = runtime().kill_switch
    if args.release:
        switch.release()
    else:
        switch.engage(args.reason)
    _print(switch.status())
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    _print({"reports": runtime().metrics.as_reports(), "som": runtime().som.stats()})
    return 0


def cmd_practice(args: argparse.Namespace) -> int:
    from osv1.learning.practice import PracticeSession

    session = PracticeSession(project_path=args.project)
    report = session.run()
    _print(report)
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    from osv1.learning.personalization import Personalization

    personalization = Personalization(workspace=args.workspace).load()
    if args.report:
        _print(personalization.weekly_report())
        return 0
    _print(personalization.run_session())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from osv1.interface.api import app

    print(f"OS_V1 local API on http://{args.host}:{args.port} — the live console is at /")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    from osv1.config import MODEL_NAME, PRODUCT, VERSION

    _print({"product": PRODUCT, "model": MODEL_NAME, "version": VERSION, "agents": len(REGISTRY)})
    return 0


# ── parser ─────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oss-v1", description="OSS Work / OS_V1 — the local unified model")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="propose a plan without executing anything")
    plan.add_argument("task")
    plan.add_argument("--agent", default="", help="use a specific agent id, for example A063")
    plan.set_defaults(func=cmd_plan)

    build = sub.add_parser("build", help="execute an approved plan, verify it, and deliver the result")
    build.add_argument("task")
    build.add_argument("--agent", default="")
    build.set_defaults(func=cmd_build)

    agents = sub.add_parser("agents", help="list the specialized agents")
    agents.add_argument("--domain", default="")
    agents.add_argument("--specialization", default="")
    agents.add_argument("--search", default="")
    agents.add_argument("--limit", type=int, default=50)
    agents.set_defaults(func=cmd_agents)

    agent = sub.add_parser("agent", help="show one agent")
    agent.add_argument("agent_id")
    agent.set_defaults(func=cmd_agent)

    status = sub.add_parser("status", help="what the system can do right now")
    status.set_defaults(func=cmd_status)

    memory = sub.add_parser("memory", help="read the memory")
    memory.add_argument("memory_action", nargs="?", default="list", choices=["list", "export", "delete"])
    memory.add_argument("--kind", default="")
    memory.add_argument("--entry-id", type=int, default=None, dest="entry_id")
    memory.add_argument("--limit", type=int, default=50)
    memory.set_defaults(func=cmd_memory)

    audit = sub.add_parser("audit", help="read the audit log")
    audit.add_argument("--verify", action="store_true", help="check the hash chain")
    audit.add_argument("--limit", type=int, default=30)
    audit.set_defaults(func=cmd_audit)

    grant = sub.add_parser("grant", help="give a permission scope")
    grant.add_argument("scope", choices=["files", "network", "programs", "irreversible"])
    grant.add_argument("target")
    grant.add_argument("--readonly", action="store_true")
    grant.set_defaults(func=cmd_grant)

    revoke = sub.add_parser("revoke", help="take a permission back")
    revoke.add_argument("scope", choices=["files", "network", "programs", "irreversible"])
    revoke.add_argument("target", nargs="?", default="")
    revoke.set_defaults(func=cmd_revoke)

    approvals = sub.add_parser("approvals", help="list or decide approvals")
    approvals.add_argument("approval_id", nargs="?", default="")
    approvals.add_argument("--reject", action="store_true")
    approvals.set_defaults(func=cmd_approvals)

    kill = sub.add_parser("kill", help="engage or release the kill switch")
    kill.add_argument("--release", action="store_true")
    kill.add_argument("--reason", default="requested from the command line")
    kill.set_defaults(func=cmd_kill)

    metrics = sub.add_parser("metrics", help="the measurable metrics of the last run")
    metrics.set_defaults(func=cmd_metrics)

    practice = sub.add_parser("practice", help="run a practice session on a local project")
    practice.add_argument("project")
    practice.set_defaults(func=cmd_practice)

    weekly = sub.add_parser("weekly", help="run or report the weekly personalization session")
    weekly.add_argument("--report", action="store_true")
    weekly.add_argument("--workspace", default=".")
    weekly.set_defaults(func=cmd_weekly)

    serve = sub.add_parser("serve", help="start the local API and the live console")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.set_defaults(func=cmd_serve)

    version = sub.add_parser("version", help="the product and model version")
    version.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
