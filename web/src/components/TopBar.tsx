"use client";

import { Search, ShieldCheck } from "lucide-react";
import { useState } from "react";

export default function TopBar() {
  const [query, setQuery] = useState("");
  return (
    <header className="topbar">
      <label className="search" aria-label="Search console">
        <Search size={15} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the console" />
      </label>
      <div className="top-actions">
        <span className="badge"><span className="status-dot" /> Local runtime</span>
        <span className="badge"><ShieldCheck size={13} /> Safe mode</span>
      </div>
    </header>
  );
}
