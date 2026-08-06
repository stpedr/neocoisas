"use client";

import { useCallback, useEffect, useState } from "react";
import { api, BoardPayload, Card, Column } from "../lib/api";
import { Skeleton, useToast } from "./Toast";

const PRIO_MAP: Record<string, string> = {
  alta: "alta", "média": "media", media: "media", baixa: "baixa",
};
function cardPriority(labels: string[]): string | null {
  const l = labels.find((x) => x.startsWith("prioridade:"));
  return l ? PRIO_MAP[l.split(":")[1]] ?? null : null;
}

export default function KanbanView() {
  const [columns, setColumns] = useState<Column[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const toast = useToast();
  const setError = (m: string) => toast(m, "error");
  const [loading, setLoading] = useState(true);

  const [dragId, setDragId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);

  // Novo cartão
  const [newTitle, setNewTitle] = useState("");
  const [newCol, setNewCol] = useState("backlog");

  const load = useCallback(async () => {
    try {
      const data: BoardPayload = await api.getBoard();
      setColumns(data.columns);
      setCards(data.cards);
      if (data.columns.length) setNewCol((c) => c || data.columns[0].id);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function moveCard(id: string, column: string) {
    const card = cards.find((c) => c.id === id);
    if (!card || card.column === column) return;
    // Otimista
    setCards((prev) =>
      prev.map((c) => (c.id === id ? { ...c, column } : c))
    );
    try {
      await api.updateCard(id, { column });
    } catch (e) {
      setError((e as Error).message);
      load(); // reverte para o estado do servidor
    }
  }

  async function addCard() {
    if (!newTitle.trim()) return;
    try {
      await api.createCard({ title: newTitle, column: newCol });
      setNewTitle("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function removeCard(id: string) {
    setCards((prev) => prev.filter((c) => c.id !== id));
    try {
      await api.deleteCard(id);
    } catch (e) {
      setError((e as Error).message);
      load();
    }
  }

  async function resetBoard() {
    if (
      !confirm(
        "Restaurar o quadro para o planejamento de sprints padrão? Isso descarta suas alterações."
      )
    )
      return;
    try {
      const data = await api.resetBoard();
      setColumns(data.columns);
      setCards(data.cards);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const total = cards.length;
  const done = cards.filter((c) => c.column === "done").length;
  const pct = total ? Math.round((done / total) * 100) : 0;

  if (loading)
    return (
      <div className="board">
        {[0, 1, 2, 3, 4].map((i) => (
          <div className="kcol" key={i}>
            <Skeleton height={18} width="50%" />
            <Skeleton height={64} />
            <Skeleton height={64} />
          </div>
        ))}
      </div>
    );

  return (
    <div>

      <div className="topbar" style={{ marginBottom: 8 }}>
        <div>
          <strong>Planejamento — rumo à publicação</strong>
          <div className="muted">
            {done} de {total} concluídas ({pct}%)
          </div>
        </div>
        <button className="btn btn-ghost" onClick={resetBoard}>
          ↺ Restaurar plano
        </button>
      </div>
      <div className="progress">
        <span style={{ width: `${pct}%` }} />
      </div>

      {/* Novo cartão */}
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div className="field" style={{ flex: 2 }}>
            <label>Nova atividade</label>
            <input
              className="input"
              placeholder="Título do cartão"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addCard()}
            />
          </div>
          <div className="field">
            <label>Coluna</label>
            <select
              className="select"
              value={newCol}
              onChange={(e) => setNewCol(e.target.value)}
            >
              {columns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: "0 0 auto" }}>
            <button className="btn btn-primary" onClick={addCard}>
              + Adicionar
            </button>
          </div>
        </div>
      </div>

      {/* Quadro */}
      <div className="board">
        {columns.map((col) => {
          const colCards = cards
            .filter((c) => c.column === col.id)
            .sort((a, b) => a.order - b.order);
          return (
            <div
              key={col.id}
              className={`kcol ${overCol === col.id ? "drag-over" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setOverCol(col.id);
              }}
              onDragLeave={() => setOverCol((c) => (c === col.id ? null : c))}
              onDrop={(e) => {
                e.preventDefault();
                setOverCol(null);
                if (dragId) moveCard(dragId, col.id);
                setDragId(null);
              }}
            >
              <div className="kcol-head">
                <span>{col.label}</span>
                <span className="kcol-count">{colCards.length}</span>
              </div>
              {colCards.map((card) => {
                const prio = cardPriority(card.labels);
                return (
                <div
                  key={card.id}
                  className={`kcard ${dragId === card.id ? "dragging" : ""} ${prio ? `prio-${prio}` : ""}`}
                  draggable
                  onDragStart={() => setDragId(card.id)}
                  onDragEnd={() => {
                    setDragId(null);
                    setOverCol(null);
                  }}
                >
                  <div className="kcard-title">{card.title}</div>
                  {card.description && (
                    <div className="kcard-desc">{card.description}</div>
                  )}
                  <div className="kcard-foot">
                    <div className="chips">
                      {prio && (
                        <span className={`chip chip-${prio}`}>{prio}</span>
                      )}
                      {card.labels
                        .filter((l) => !l.startsWith("prioridade:"))
                        .map((l) => (
                          <span className="chip" key={l}>
                            {l}
                          </span>
                        ))}
                    </div>
                    <button
                      className="kcard-del"
                      title="Excluir"
                      onClick={() => removeCard(card.id)}
                    >
                      🗑
                    </button>
                  </div>
                  {card.sprint && (
                    <div className="sprint-tag" style={{ marginTop: 6 }}>
                      {card.sprint}
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
