export type AgentState = "ready" | "simulated" | "approval";

export type Agent = {
  id: string;
  name: string;
  description: string;
  state: AgentState;
  latency: string;
};

export const agents: Agent[] = [
  { id: "orchestrator", name: "Orchestrator", description: "Bounded task decomposition", state: "ready", latency: "local" },
  { id: "security", name: "Security review", description: "Local pattern checks", state: "ready", latency: "local" },
  { id: "code", name: "Code assistant", description: "Generate and review only", state: "ready", latency: "local" },
  { id: "files", name: "Files", description: "Root-confined operations", state: "approval", latency: "local" },
  { id: "browser", name: "Browser", description: "Preview and simulation", state: "simulated", latency: "off" },
  { id: "integrations", name: "Integrations", description: "No outbound delivery", state: "simulated", latency: "off" },
  { id: "memory", name: "Memory", description: "Per-user SQLite store", state: "ready", latency: "local" },
  { id: "learning", name: "Learning", description: "Request-scoped statistics", state: "ready", latency: "local" },
];

export const activity = [
  { label: "Policy check completed", detail: "No external action attempted", time: "just now", tone: "good" },
  { label: "Security scan ready", detail: "Local pattern checks available", time: "2 min", tone: "good" },
  { label: "Browser adapter paused", detail: "Simulation-only boundary", time: "6 min", tone: "muted" },
  { label: "Filesystem scope verified", detail: "Allowed root is configured", time: "11 min", tone: "good" },
];
