"use client";

import { useState } from "react";
import IdeasView from "./components/IdeasView";
import KanbanView from "./components/KanbanView";

type Tab = "ideas" | "kanban";

export default function Home() {
  const [tab, setTab] = useState<Tab>("ideas");

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand">
          <span className="logo">🎬</span>
          <span>Auto Niche Engine</span>
        </div>
        <div className="tabs" role="tablist">
          <button
            className={`tab ${tab === "ideas" ? "active" : ""}`}
            onClick={() => setTab("ideas")}
          >
            💡 Ideias
          </button>
          <button
            className={`tab ${tab === "kanban" ? "active" : ""}`}
            onClick={() => setTab("kanban")}
          >
            🗂️ Kanban
          </button>
        </div>
      </div>

      {tab === "ideas" ? <IdeasView /> : <KanbanView />}
    </div>
  );
}
