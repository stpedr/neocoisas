"use client";

import { useState } from "react";
import IdeasView from "./components/IdeasView";
import KanbanView from "./components/KanbanView";
import ScheduleView from "./components/ScheduleView";
import ModelsView from "./components/ModelsView";
import DashboardView from "./components/DashboardView";
import { ToastProvider } from "./components/Toast";

type Tab = "ideas" | "kanban" | "schedule" | "models" | "dashboard";

const TABS: { id: Tab; label: string }[] = [
  { id: "ideas", label: "💡 Ideias" },
  { id: "kanban", label: "🗂️ Kanban" },
  { id: "schedule", label: "⏱️ Agendamento" },
  { id: "models", label: "⚙️ Modelos" },
  { id: "dashboard", label: "📊 Dashboard" },
];

export default function Home() {
  const [tab, setTab] = useState<Tab>("ideas");

  return (
    <ToastProvider>
    <div className="container">
      <div className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>🎬</span>
          <span>Auto Niche Engine</span>
        </div>
        <div className="tabs" role="tablist" aria-label="Seções">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              className={`tab ${tab === t.id ? "active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel">
        {tab === "ideas" && <IdeasView />}
        {tab === "kanban" && <KanbanView />}
        {tab === "schedule" && <ScheduleView />}
        {tab === "models" && <ModelsView />}
        {tab === "dashboard" && <DashboardView />}
      </div>
    </div>
    </ToastProvider>
  );
}
