"use client";

// REMOTE NO CELULAR (F6): controlar o show sem o editor.
//
// Pareamento: o editor mostra um QR com http://<ip-do-mestre>:8100/remote/#t=<token>.
// O token fica no localStorage e vai em todo pedido (ver lib/api.ts). Também dá
// para digitar o token à mão. "Adicionar à tela inicial" instala como app (PWA).
//
// Cada comando é pequeno e idempotente (PATCH de uma superfície, recall de um
// look), para conviver com o editor aberto no PC ao mesmo tempo.

import { useCallback, useEffect, useRef, useState } from "react";
import { adoptTokenFromHash, api, ApiError, getToken, setToken } from "../lib/api";
import MediaGallery from "../components/MediaGallery";
import ColorControls, { PRESETS } from "../components/ColorControls";
import type { MediaItem, Pattern, Project, SourceSpec, Surface } from "../lib/types";
import { DEFAULT_COLOR } from "../lib/types";

type Conn = "ok" | "offline" | "unpaired";
type Tab = "show" | "surfaces" | "capture";

const PATTERNS: { value: Pattern; label: string }[] = [
  { value: "none", label: "Show" },
  { value: "white", label: "Branco" },
  { value: "grid", label: "Grade" },
  { value: "edges", label: "Bordas" },
];

export default function RemotePage() {
  const [project, setProject] = useState<Project | null>(null);
  const [conn, setConn] = useState<Conn>("ok");
  const [nodeId, setNodeId] = useState("");
  const [tab, setTab] = useState<Tab>("show");
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "err" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [gallerySurface, setGallerySurface] = useState<Surface | null>(null);
  const rev = useRef(-1);
  // Dentro do app Android (Capacitor) o user agent leva "ProjMapApp": mostra
  // "Trocar mestre", que volta ao lançador do app (origem https://localhost).
  const [inApp, setInApp] = useState(false);
  // Enquanto o dedo está num slider, a sincronia não sobrescreve o valor local.
  const dragging = useRef(false);

  const notify = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    setToast({ msg, kind });
    window.setTimeout(() => setToast(null), 3000);
  }, []);

  const apply = useCallback((payload: { revision: number; project: Project }) => {
    rev.current = payload.revision;
    setProject(payload.project);
    setNodeId((cur) => cur || payload.project.nodes[0]?.id || "");
  }, []);

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) return setConn("unpaired");
      if (e instanceof ApiError) return notify(e.message, "err");
      setConn("offline");
    },
    [notify],
  );

  const run = useCallback(
    async (fn: () => Promise<{ revision: number; project: Project }>, okMsg?: string) => {
      try {
        apply(await fn());
        setConn("ok");
        if (okMsg) notify(okMsg);
      } catch (e) {
        fail(e);
      }
    },
    [apply, fail, notify],
  );

  // ---- carga + sincronia por revisão
  const refresh = useCallback(async () => {
    try {
      const { revision } = await api.health();
      if (revision !== rev.current && !dragging.current) apply(await api.getProject());
      setConn("ok");
    } catch (e) {
      fail(e);
    }
  }, [apply, fail]);

  useEffect(() => {
    adoptTokenFromHash();
    setInApp(navigator.userAgent.includes("ProjMapApp"));
    void refresh();
    const id = window.setInterval(refresh, 2000);
    return () => window.clearInterval(id);
  }, [refresh]);

  if (conn === "unpaired") return <PairScreen onPaired={() => { setConn("ok"); rev.current = -1; void refresh(); }} />;
  if (!project) {
    return (
      <main className="center-msg">
        {conn === "offline" ? "Mestre fora do ar. Mesma rede Wi-Fi? Tentando de novo…" : "Conectando ao mestre…"}
      </main>
    );
  }

  const node = project.nodes.find((n) => n.id === nodeId) ?? project.nodes[0];
  const out = node.output;
  const surfaces = project.surfaces.filter((s) => s.node_id === node.id).sort((a, b) => b.z - a.z);

  const patchOutput = (changes: Partial<typeof out>) => run(() => api.patchOutput(node.id, changes));

  return (
    <main className="remote">
      <header className="remote-head">
        <span className={`dot ${conn === "ok" ? "" : "dot-off"}`} title={conn === "ok" ? "conectado" : "sem conexão"} />
        <strong className="remote-title">{project.name}</strong>
        {project.nodes.length > 1 && (
          <select value={node.id} onChange={(e) => setNodeId(e.target.value)} aria-label="Projetor">
            {project.nodes.map((n) => (
              <option key={n.id} value={n.id}>{n.name || n.id}</option>
            ))}
          </select>
        )}
        {inApp && <a className="btn btn-small" href="https://localhost/?pick=1">Trocar mestre</a>}
      </header>

      <button
        className={`blackout ${out.blackout ? "blackout-on" : ""}`}
        onClick={() => patchOutput({ blackout: !out.blackout })}
      >
        {out.blackout ? "● BLACKOUT — toque para voltar" : "Blackout"}
      </button>

      <nav className="segmented remote-tabs">
        {(["show", "surfaces", "capture"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
            {{ show: "Show", surfaces: "Superfícies", capture: "Foto/Mídia" }[t]}
          </button>
        ))}
      </nav>

      {tab === "show" && (
        <>
          <section className="card">
            <h2>Dimmer</h2>
            <Slider
              value={out.intensity}
              onDrag={(v) => (dragging.current = v)}
              onCommit={(v) => patchOutput({ intensity: v })}
            />
          </section>

          <section className="card">
            <h2>Saída</h2>
            <div className="segmented">
              {PATTERNS.map((p) => (
                <button key={p.value} className={out.pattern === p.value ? "on" : ""}
                        onClick={() => patchOutput({ pattern: p.value })}>
                  {p.label}
                </button>
              ))}
            </div>
            <label className="toggle">
              <input type="checkbox" checked={out.show_outlines}
                     onChange={(e) => patchOutput({ show_outlines: e.target.checked })} />
              Contornos das superfícies
            </label>
          </section>

          <section className="card">
            <h2>Imagem</h2>
            <div className="preset-grid">
              {PRESETS.map((p) => (
                <button key={p.name} className="btn btn-small" title={p.hint} onClick={() => patchOutput({ color: { ...p.color } })}>
                  {p.name}
                </button>
              ))}
            </div>
            <ColorControls compact value={out.color ?? DEFAULT_COLOR} onChange={(c) => patchOutput({ color: c })} />
            <label className="toggle">
              <input type="checkbox" checked={out.flip_h} onChange={(e) => patchOutput({ flip_h: e.target.checked })} />
              Retroprojeção (espelhar)
            </label>
          </section>

          <Looks project={project} run={run} notify={notify} fail={fail} apply={apply} />
          <InteractCard onError={(m) => notify(m, "err")} />
        </>
      )}

      {tab === "surfaces" && (
        <section className="remote-list">
          {surfaces.length === 0 && <p className="dim">Nenhuma superfície neste projetor. Crie no editor.</p>}
          {surfaces.map((s) => (
            <SurfaceCard key={s.id} surface={s} media={project.media}
                         onDrag={(v) => (dragging.current = v)}
                         onGallery={() => setGallerySurface(s)}
                         onPatch={(changes) => run(() => api.patchSurface(s.id, changes))} />
          ))}
        </section>
      )}

      {tab === "capture" && (
        <section className="card">
          <h2>Foto da posição do projetor</h2>
          <p className="dim small">
            Fique no lugar do projetor e fotografe a parede. A foto substitui a do {node.name || node.id} no editor.
          </p>
          <label className="btn btn-accent btn-block">
            📷 Tirar foto
            <input type="file" accept="image/*" capture="environment" hidden disabled={busy}
                   onChange={async (e) => {
                     const f = e.target.files?.[0];
                     e.target.value = "";
                     if (!f) return;
                     setBusy(true);
                     await run(() => api.uploadPhoto(node.id, f), "Foto enviada. Ajuste os cantos no editor.");
                     setBusy(false);
                   }} />
          </label>

          <h2>Enviar mídia</h2>
          <p className="dim small">Vídeo, GIF ou imagem do celular. Depois escolha em Superfícies.</p>
          <label className="btn btn-block">
            ⬆ Escolher arquivo
            <input type="file" accept="video/*,image/*" hidden disabled={busy}
                   onChange={async (e) => {
                     const f = e.target.files?.[0];
                     e.target.value = "";
                     if (!f) return;
                     setBusy(true);
                     try {
                       await api.uploadMedia(f);
                       apply(await api.getProject());
                       notify(`"${f.name}" enviado`);
                     } catch (err) {
                       fail(err);
                     }
                     setBusy(false);
                   }} />
          </label>
          {busy && <p className="dim small">Enviando…</p>}
        </section>
      )}

      <MediaGallery
        open={!!gallerySurface}
        title={gallerySurface ? `Mídia de "${gallerySurface.label || gallerySurface.id}"` : undefined}
        surfaceId={gallerySurface?.id}
        onPick={(m) => {
          const s = gallerySurface;
          if (s) void run(() => api.patchSurface(s.id, { source: { kind: m.kind, media: m.sha256 } }), "Mídia trocada");
        }}
        onClose={() => setGallerySurface(null)}
        onError={(m) => notify(m, "err")}
      />

      {conn === "offline" && <div className="toast toast-err" role="status">Sem conexão com o mestre…</div>}
      {toast && <div className={`toast toast-${toast.kind}`} role="status">{toast.msg}</div>}
    </main>
  );
}

// --------------------------------------------------------------------- partes
function PairScreen({ onPaired }: { onPaired: () => void }) {
  const [value, setValue] = useState(getToken());
  const [inApp, setInApp] = useState(false);
  useEffect(() => setInApp(navigator.userAgent.includes("ProjMapApp")), []);
  return (
    <main className="remote">
      <section className="card">
        <h2>Parear com o mestre</h2>
        <p className="dim small">
          Escaneie o QR do card <b>Remote</b> no editor, ou digite o token que o mestre mostrou no terminal.
        </p>
        <input value={value} onChange={(e) => setValue(e.target.value.trim())} placeholder="token"
               autoCapitalize="off" autoCorrect="off" spellCheck={false} />
        <button className="btn btn-accent" disabled={!value} onClick={() => { setToken(value); onPaired(); }}>
          Conectar
        </button>
        {inApp && <a className="btn" href="https://localhost/?pick=1">Escolher outro mestre</a>}
      </section>
    </main>
  );
}

function Slider({ value, onCommit, onDrag }: {
  value: number; onCommit: (v: number) => void; onDrag: (dragging: boolean) => void;
}) {
  const [local, setLocal] = useState(value);
  const held = useRef(false);
  const last = useRef(0);
  useEffect(() => {
    if (!held.current) setLocal(value);
  }, [value]);
  return (
    <div className="remote-slider">
      <input
        type="range" min={0} max={1} step={0.01} value={local}
        onPointerDown={() => { held.current = true; onDrag(true); }}
        onPointerUp={() => { held.current = false; onDrag(false); onCommit(local); }}
        onChange={(e) => {
          const v = Number(e.target.value);
          setLocal(v);
          // ~8 comandos/s enquanto arrasta: a parede acompanha sem afogar o Wi-Fi.
          const now = Date.now();
          if (now - last.current > 120) {
            last.current = now;
            onCommit(v);
          }
        }}
      />
      <span className="remote-value">{Math.round(local * 100)}%</span>
    </div>
  );
}


function SurfaceCard({ surface, media, onPatch, onDrag, onGallery }: {
  surface: Surface;
  media: Record<string, MediaItem>;
  onPatch: (c: { visible?: boolean; opacity?: number; source?: Partial<SourceSpec> }) => void;
  onDrag: (dragging: boolean) => void;
  onGallery: () => void;
}) {
  const cur = surface.source.media ? media[surface.source.media] : undefined;
  return (
    <section className={`card ${surface.visible ? "" : "card-muted"}`}>
      <div className="card-head">
        <h2>{surface.label || surface.id}</h2>
        <label className="toggle">
          <input type="checkbox" checked={surface.visible} onChange={(e) => onPatch({ visible: e.target.checked })} />
          Visível
        </label>
      </div>
      {/* Galeria com miniaturas no lugar da lista suspensa (que fica enorme com muitas mídias) */}
      <button className="media-pick" onClick={onGallery}>
        {cur ? <img src={api.mediaThumbUrl(cur.sha256)} alt="" /> : <span className="media-pick-empty">🖼</span>}
        <span>
          <b>{cur ? cur.filename : { none: "Nada (preto)", test: "Cartela de teste", color: "Cor sólida", interactive: "Cena interativa", video: "Vídeo", gif: "GIF", image: "Imagem" }[surface.source.kind]}</b>
          <span className="dim small">toque para escolher na galeria</span>
        </span>
      </button>
      <div className="segmented">
        {([["none", "Preto"], ["test", "Cartela"], ["color", "Cor"], ["interactive", "Interativa"]] as const).map(([k, label]) => (
          <button key={k} className={surface.source.kind === k ? "on" : ""} onClick={() => onPatch({ source: { kind: k, media: null } })}>
            {label}
          </button>
        ))}
      </div>
      {surface.source.kind === "color" && (
        <label>
          Cor
          <input type="color" value={rgbToHex(surface.source.color)}
                 onChange={(e) => onPatch({ source: { color: hexToRgb(e.target.value) } })} />
        </label>
      )}
      <label>Opacidade</label>
      <Slider value={surface.opacity} onDrag={onDrag} onCommit={(v) => onPatch({ opacity: v })} />
    </section>
  );
}

function Looks({ project, run, notify, fail, apply }: {
  project: Project;
  run: (fn: () => Promise<{ revision: number; project: Project }>, ok?: string) => Promise<void>;
  notify: (m: string, k?: "ok" | "err") => void;
  fail: (e: unknown) => void;
  apply: (p: { revision: number; project: Project }) => void;
}) {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(false);
  // Apagar pede dois toques (o viewer não tem confirm()).
  const [armed, setArmed] = useState<string | null>(null);

  return (
    <section className="card">
      <div className="card-head">
        <h2>Looks</h2>
        {project.looks.length > 0 && (
          <button className="btn btn-small" onClick={() => { setEditing(!editing); setArmed(null); }}>
            {editing ? "Pronto" : "Editar"}
          </button>
        )}
      </div>
      {project.looks.length === 0 && (
        <p className="dim small">Monte a parede (fontes, visibilidade) e salve como look para trocar de cena com um toque.</p>
      )}
      <div className="looks">
        {project.looks.map((lk) =>
          editing ? (
            <button key={lk.id} className={`btn ${armed === lk.id ? "btn-danger" : ""}`}
                    onClick={() => {
                      if (armed !== lk.id) return setArmed(lk.id);
                      setArmed(null);
                      void run(() => api.deleteLook(lk.id), `"${lk.name}" apagado`);
                    }}>
              {armed === lk.id ? "Toque p/ apagar" : `✕ ${lk.name}`}
            </button>
          ) : (
            <button key={lk.id} className="btn look-btn"
                    onClick={async () => {
                      try {
                        const r = await api.recallLook(lk.id);
                        apply(r);
                        notify(r.skipped.length ? `${lk.name} (${r.skipped.length} ignorada(s))` : lk.name);
                      } catch (e) {
                        fail(e);
                      }
                    }}>
              {lk.name}
            </button>
          ),
        )}
      </div>
      <div className="row">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="nome do look" maxLength={80} />
        <button className="btn btn-accent"
                onClick={async () => { await run(() => api.saveLook(name), "Look salvo"); setName(""); }}>
          Salvar
        </button>
      </div>
    </section>
  );
}

function InteractCard({ onError }: { onError: (m: string) => void }) {
  const [state, setState] = useState<{ title: string; paused: boolean } | null>(null);
  useEffect(() => {
    api.interactState()
      .then((s) => setState({ title: s.spec.title, paused: s.paused }))
      .catch(() => setState(null)); // mestre sem camada interativa
  }, []);
  if (!state) return null;
  return (
    <section className="card">
      <h2>Cena interativa</h2>
      <p className="dim small">{state.title}</p>
      <button className="btn btn-block"
              onClick={async () => {
                try {
                  const s = await api.interactPause(!state.paused);
                  setState({ title: s.spec.title, paused: s.paused });
                } catch (e) {
                  onError(e instanceof ApiError ? e.message : "Falha");
                }
              }}>
        {state.paused ? "▶ Continuar" : "⏸ Pausar"}
      </button>
    </section>
  );
}

function rgbToHex([r, g, b]: [number, number, number]) {
  return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
