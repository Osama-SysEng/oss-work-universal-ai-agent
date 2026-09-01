"use client";

import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock3, Layers3, ShieldCheck, Sparkles } from "lucide-react";
import DashboardShell from "@/components/DashboardShell";
import OrchestratorFlowGraph from "@/components/OrchestratorFlowGraph";
import { activity, agents } from "@/lib/console-data";

const stats = [
  ["Registered agents", "8", "Bounded runtime graph"],
  ["Ready locally", "5", "No provider dependency"],
  ["Approval gates", "1", "Filesystem mutations"],
  ["External actions", "0", "Simulation-only release"],
];

const stateLabel = { ready: "Ready", simulated: "Simulated", approval: "Approval" };

export default function Home() {
  return <DashboardShell>
    <section className="hero">
      <div><div className="eyebrow">OSS Work / operator console</div><h1>One clear place to understand what the system can do.</h1><p className="lede">A local-first multi-agent foundation with explicit boundaries. Review work, inspect the agent graph, and approve mutations only when the context is clear.</p></div>
      <div className="hero-side"><strong><span className="status-dot" /> Safe release active</strong>External actions are paused. Every decision exposes its policy result and whether an action was attempted.</div>
    </section>

    <section className="stats" aria-label="Runtime summary">{stats.map(([label, value, note]) => <div className="card stat-card" key={label}><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-note">{note}</div></div>)}</section>

    <div className="grid">
      <section className="card panel" aria-labelledby="agents-title"><div className="panel-head"><div><div className="panel-title" id="agents-title">Agent fleet</div><div className="panel-kicker">Capability status, not permission status</div></div><Layers3 size={16} color="var(--accent)" /></div><div className="agent-grid">{agents.map((agent) => <button className="agent" key={agent.id}><div className="agent-top"><span>{agent.id.toUpperCase()}</span><ArrowUpRight size={13} /></div><div className="agent-name">{agent.name}</div><div className="agent-desc">{agent.description}</div><div className="agent-state">{stateLabel[agent.state]} · {agent.latency}</div></button>)}</div></section>
      <section className="card panel" aria-labelledby="activity-title"><div className="panel-head"><div><div className="panel-title" id="activity-title">Recent activity</div><div className="panel-kicker">Local audit stream</div></div><Clock3 size={16} color="var(--accent-2)" /></div><div className="activity-list">{activity.map((item) => <div className="activity" key={item.label}><span className="activity-dot" /><div className="activity-text"><strong>{item.label}</strong><br /><span className="panel-kicker">{item.detail}</span></div><span className="activity-meta">{item.time}</span></div>)}</div><div className="notice"><AlertTriangle size={16} /><span><strong>Review before enabling.</strong> The UI never turns a simulation into a live action. Provider adapters and host code execution require a separate commissioning process.</span></div></section>
    </div>

    <OrchestratorFlowGraph agents={agents} />
    <p className="footer-note"><CheckCircle2 size={13} color="var(--accent)" /> Console state is illustrative until connected to a reviewed backend. No live credentials are expected by the frontend.</p>
  </DashboardShell>;
}
