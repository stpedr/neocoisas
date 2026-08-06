"use client";

import { useEffect, useState } from "react";
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
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    const saved = (localStorage.getItem("theme") as "light" | "dark" | null);
    const initial =
      saved ??
      (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    setTheme(initial);
    document.documentElement.dataset.theme = initial;
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
  }

  return (
    <ToastProvider>
    <div className="container">
      <div className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>🎬</span>
          <span>Auto Niche Engine</span>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
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
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label="Alternar tema claro/escuro"
            title="Tema claro/escuro"
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
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
