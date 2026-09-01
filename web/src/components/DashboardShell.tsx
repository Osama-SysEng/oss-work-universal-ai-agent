import type { ReactNode } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

export default function DashboardShell({ children }: { children: ReactNode }) {
  return <div className="shell"><Sidebar /><div className="content"><TopBar /><main className="main">{children}</main></div></div>;
}
