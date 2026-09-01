"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bot, Database, FolderLock, LayoutDashboard, Network, Settings, ShieldCheck, Sparkles, Terminal } from "lucide-react";

const items = [
  ["/", "Overview", LayoutDashboard],
  ["/agents", "Agent fleet", Bot],
  ["/security", "Security", ShieldCheck],
  ["/memory", "Memory", Database],
  ["/architecture", "Architecture", Network],
  ["/settings", "Settings", Settings],
] as const;

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brand">
        <span className="brand-mark"><Sparkles size={16} /></span>
        <span className="brand-copy"><span className="brand-title">OSS Work</span><span className="brand-subtitle">Operator console</span></span>
      </Link>
      <nav className="nav" aria-label="Primary navigation">
        {items.map(([href, label, Icon]) => (
          <Link key={href} href={href} className={`nav-link ${pathname === href ? "active" : ""}`}>
            <Icon size={16} strokeWidth={1.8} /><span>{label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-note"><strong><Activity size={13} /> Safe release</strong>Mutations require approval. External adapters are paused by default.</div>
    </aside>
  );
}
