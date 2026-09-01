"use client";

import { useState } from "react";
import { BrainCircuit, Code2, Cpu, Database, FolderLock, Globe2, Link2, ShieldCheck } from "lucide-react";
import type { Agent } from "@/lib/console-data";

const icons = { orchestrator: Cpu, security: ShieldCheck, code: Code2, files: FolderLock, browser: Globe2, integrations: Link2, memory: Database, learning: BrainCircuit };

export default function OrchestratorFlowGraph({ agents }: { agents: Agent[] }) {
  const [selected, setSelected] = useState("orchestrator");
  return (
    <section className="card panel flow" aria-labelledby="flow-title">
      <div className="panel-head"><div><div className="panel-title" id="flow-title">Coordination map</div><div className="panel-kicker">A bounded view of the active runtime graph</div></div><span className="badge">8 registered agents</span></div>
      <div className="flow-canvas">
        <div className="flow-grid" />
        <svg className="flow-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><line x1="50" y1="30" x2="12" y2="78" stroke="#61d7c4" strokeWidth=".3" /><line x1="50" y1="30" x2="38" y2="78" stroke="#61d7c4" strokeWidth=".3" /><line x1="50" y1="30" x2="63" y2="78" stroke="#61d7c4" strokeWidth=".3" /><line x1="50" y1="30" x2="88" y2="78" stroke="#61d7c4" strokeWidth=".3" /></svg>
        <div className="flow-master"><strong>Orchestrator</strong><span>Decomposition · bounded delegation · result synthesis</span></div>
        <div className="flow-nodes">
          {agents.filter((agent) => agent.id !== "orchestrator").slice(0, 8).map((agent) => { const Icon = icons[agent.id as keyof typeof icons] ?? Cpu; return <button key={agent.id} className={`flow-node ${selected === agent.id ? "selected" : ""}`} onClick={() => setSelected(agent.id)}><Icon size={14} color={selected === agent.id ? "#61d7c4" : "#93a2b5"} /><strong>{agent.name}</strong><span>{agent.state === "simulated" ? "simulation" : agent.state === "approval" ? "approval gate" : "ready"}</span></button>; })}
        </div>
      </div>
      <div className="footer-note">Selected: <strong>{agents.find((agent) => agent.id === selected)?.name}</strong>. The graph describes capabilities; policy still decides whether an action may proceed.</div>
    </section>
  );
}
