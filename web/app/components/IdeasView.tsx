"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Counts, Idea } from "../lib/api";
import { useToast } from "./Toast";

export default function IdeasView() {
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<"manual" | "auto">("manual");
  const [count, setCount] = useState(5);
  const [numScenes, setNumScenes] = useState(5);

  const [pending, setPending] = useState<Idea[]>([]);
  const [approved, setApproved] = useState<Idea[]>([]);
  const [counts, setCounts] = useState<Counts>({});
  const [leaving, setLeaving] = useState<{ id: string; dir: "left" | "right" } | null>(
    null
  );

  const [loading, setLoading] = useState(false);
  const toast = useToast();
  const setError = (m: string) => toast(m, "error");
  const setOk = (m: string) => toast(m, "ok");

  const refresh = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        api.listIdeas("pending"),
        api.listIdeas("approved"),
      ]);
      setPending(p.ideas);
      setApproved(a.ideas);
      setCounts(a.counts);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function generate() {
    if (!prompt.trim()) return;
    setLoading(true);
    setError("");
    setOk("");
    try {
      const res = await api.generate({ prompt, mode, count, num_scenes: numScenes });
      if (mode === "auto") {
        setOk(
          `${res.generated} ideias geradas e aprovadas automaticamente. ` +
            "Conecte um publisher (API oficial) para postar de fato."
        );
      } else {
        setOk(`${res.generated} ideias geradas. Aprove ou rejeite abaixo.`);
      }
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const decide = useCallback(
    (idea: Idea, dir: "left" | "right") => {
      if (leaving) return;
      setLeaving({ id: idea.id, dir });
      setTimeout(async () => {
        try {
          if (dir === "right") await api.approve(idea.id);
          else await api.reject(idea.id);
          setPending((prev) => prev.filter((i) => i.id !== idea.id));
          const a = await api.listIdeas("approved");
          setApproved(a.ideas);
          setCounts(a.counts);
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setLeaving(null);
        }
      }, 320);
    },
    [leaving]
  );

  // Atalhos de teclado: ← rejeita, → aprova.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!pending.length || leaving) return;
      if (e.key === "ArrowLeft") decide(pending[0], "left");
      if (e.key === "ArrowRight") decide(pending[0], "right");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, leaving, decide]);

  const [renderingId, setRenderingId] = useState<string | null>(null);

  async function markPosted(id: string) {
    try {
      await api.post(id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function renderVideo(id: string) {
    setRenderingId(id);
    setError("");
    try {
      await api.render(id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRenderingId(null);
    }
  }

  const deck = pending.slice(0, 3);

  return (
    <div>
      {/* Formulário do prompt */}
      <div className="panel">
        <div className="field">
          <label>Seu prompt / tema</label>
          <textarea
            className="textarea"
            placeholder="Ex: curiosidades sobre o espaço para crianças"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>
        <div className="row">
          <div className="field" style={{ flex: "0 0 auto" }}>
            <label>Modo</label>
            <div className="mode-toggle">
              <button
                className={mode === "manual" ? "on" : ""}
                onClick={() => setMode("manual")}
                type="button"
              >
                🃏 Manual (Tinder)
              </button>
              <button
                className={mode === "auto" ? "on" : ""}
                onClick={() => setMode("auto")}
                type="button"
              >
                ⚡ Auto (prompta-e-posta)
              </button>
            </div>
            <span className="hint">
              {mode === "manual"
                ? "Você aprova/rejeita cada ideia antes de postar."
                : "Ideias já entram aprovadas; postagem via API oficial (gancho)."}
            </span>
          </div>
          <div className="field">
            <label>Nº de ideias</label>
            <input
              className="input"
              type="number"
              min={1}
              max={12}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
          </div>
          <div className="field">
            <label>Cenas por vídeo</label>
            <input
              className="input"
              type="number"
              min={1}
              max={12}
              value={numScenes}
              onChange={(e) => setNumScenes(Number(e.target.value))}
            />
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={generate}
          disabled={loading || !prompt.trim()}
        >
          {loading && <span className="spinner" />}
          {loading ? "Gerando na sua GPU (Ollama)..." : "Gerar ideias"}
        </button>
      </div>

      {/* Contadores */}
      <div className="stats">
        <div className="stat">
          <div className="num">{counts.pending ?? 0}</div>
          <div className="lbl">Pendentes</div>
        </div>
        <div className="stat">
          <div className="num">{counts.approved ?? 0}</div>
          <div className="lbl">Aprovadas</div>
        </div>
        <div className="stat">
          <div className="num">{counts.posted ?? 0}</div>
          <div className="lbl">Postadas</div>
        </div>
        <div className="stat">
          <div className="num">{counts.rejected ?? 0}</div>
          <div className="lbl">Rejeitadas</div>
        </div>
      </div>

      {/* Deck Tinder */}
      <div className="section-title">Revisão de ideias</div>
      {pending.length === 0 ? (
        <div className="empty">
          Nenhuma ideia pendente. Gere ideias no modo manual para revisar aqui.
        </div>
      ) : (
        <>
          <div className="deck">
            {deck
              .map((idea, i) => {
                const isTop = i === 0;
                const cls = isTop
                  ? leaving?.id === idea.id
                    ? `swipe-card leaving-${leaving.dir}`
                    : "swipe-card"
                  : "swipe-card behind";
                return (
                  <div
                    key={idea.id}
                    className={cls}
                    style={{ zIndex: deck.length - i }}
                  >
                    <span className="card-badge">
                      {idea.mode === "auto" ? "auto" : "manual"} ·{" "}
                      {idea.scenes.length} cenas
                    </span>
                    <div className="card-title">{idea.title}</div>
                    {idea.note && <div className="hint">{idea.note}</div>}
                    <div className="scenes">
                      {idea.scenes.length === 0 && (
                        <div className="muted">
                          (Roteiro não gerado — veja a observação acima.)
                        </div>
                      )}
                      {idea.scenes.map((s, idx) => (
                        <div className="scene" key={idx}>
                          <div className="n">
                            {idx + 1}. {s.narration || "—"}
                          </div>
                          {s.visual_prompt && (
                            <div className="v">🎨 {s.visual_prompt}</div>
                          )}
                          <div className="d">{s.duration_s}s</div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
              .reverse()}
          </div>
          <div className="deck-actions">
            <button
              className="circle no"
              onClick={() => decide(pending[0], "left")}
              title="Rejeitar (←)"
            >
              ✕
            </button>
            <button
              className="circle yes"
              onClick={() => decide(pending[0], "right")}
              title="Aprovar (→)"
            >
              ♥
            </button>
          </div>
          <p className="muted" style={{ textAlign: "center", marginTop: 10 }}>
            Dica: use as setas ← / → do teclado.
          </p>
        </>
      )}

      {/* Aprovadas prontas para postar */}
      <div className="section-title">
        Aprovadas — prontas para postar ({approved.length})
      </div>
      {approved.length === 0 ? (
        <p className="muted">Nenhuma ideia aprovada ainda.</p>
      ) : (
        approved.map((idea) => (
          <div className="approved-item" key={idea.id} style={{ flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <strong>{idea.title}</strong>
              <div className="muted">
                {idea.scenes.length} cenas · {idea.mode}
                {idea.video_path ? " · 🎬 vídeo pronto" : ""}
              </div>
              {idea.video_path && (
                <video
                  key={idea.video_path}
                  controls
                  style={{ marginTop: 8, width: 180, borderRadius: 8 }}
                  src={api.videoUrl(idea.id)}
                />
              )}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn"
                onClick={() => renderVideo(idea.id)}
                disabled={renderingId === idea.id}
              >
                {renderingId === idea.id && <span className="spinner" />}
                {idea.video_path ? "Re-renderizar" : "Renderizar vídeo"}
              </button>
              <button className="btn" onClick={() => markPosted(idea.id)}>
                Marcar como postado
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
