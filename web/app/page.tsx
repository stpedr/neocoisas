"use client";

import { useState } from "react";
import IdeasView from "./components/IdeasView";
import KanbanView from "./components/KanbanView";
import ScheduleView from "./components/ScheduleView";
import ModelsView from "./components/ModelsView";
import DashboardView from "./components/DashboardView";

type Tab = "ideas" | "kanban" | "schedule" | "models" | "dashboard";

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
          <button
            className={`tab ${tab === "schedule" ? "active" : ""}`}
            onClick={() => setTab("schedule")}
          >
            ⏱️ Agendamento
          </button>
          <button
            className={`tab ${tab === "models" ? "active" : ""}`}
            onClick={() => setTab("models")}
          >
            ⚙️ Modelos
          </button>
          <button
            className={`tab ${tab === "dashboard" ? "active" : ""}`}
            onClick={() => setTab("dashboard")}
          >
            📊 Dashboard
          </button>
        </div>
      </div>

      {tab === "ideas" && <IdeasView />}
      {tab === "kanban" && <KanbanView />}
      {tab === "schedule" && <ScheduleView />}
      {tab === "models" && <ModelsView />}
      {tab === "dashboard" && <DashboardView />}
    </div>
  );
}
