"use client";

// Galeria de mídias: substitui as listas suspensas, que ficam enormes.
//
// Duas origens:
//  - "No projeto": o que já foi enviado/importado;
//  - "Minhas pastas": a biblioteca do mestre (ex.: a pasta do Google Drive
//    sincronizada no PC). Escolher daqui importa o arquivo para o projeto.
// Com uma superfície em foco, mostra no topo as "Sugeridas" (formato,
// resolução, tipo), com o motivo de cada uma.

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { LibraryItem, MediaInfo, MediaItem, MediaKind, Suggestion } from "../lib/types";

interface Props {
  open: boolean;
  title?: string;
  surfaceId?: string | null; // para as sugestões
  onPick: (item: MediaItem) => void;
  onClose: () => void;
  onError: (msg: string) => void;
}

type Tab = "project" | "library";
type Card = {
  key: string;
  name: string;
  kind: MediaKind;
  folder: string;
  duration: number;
  width: number;
  height: number;
  thumb: string;
  pick: () => Promise<MediaItem>;
};

const KIND_LABEL: Record<MediaKind, string> = { video: "Vídeo", gif: "GIF", image: "Foto" };

export default function MediaGallery({ open, title, surfaceId, onPick, onClose, onError }: Props) {
  const [tab, setTab] = useState<Tab>("project");
  const [project, setProject] = useState<MediaInfo[]>([]);
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [hasRoots, setHasRoots] = useState(true);
  const [kind, setKind] = useState<MediaKind | "all">("all");
  const [folder, setFolder] = useState("");
  const [q, setQ] = useState("");
  const [sugg, setSugg] = useState<Suggestion[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async (rescan = false) => {
    setLoading(true);
    try {
      const [p, l] = await Promise.all([api.mediaInfo(), api.library(rescan)]);
      setProject(p.items);
      setLibrary(l.items);
      setFolders(l.folders);
      setHasRoots(l.roots.length > 0);
      if (!p.items.length && l.items.length) setTab("library");
      if (surfaceId) {
        const s = await api.suggest([surfaceId]);
        setSugg(s.suggestions[surfaceId]?.ranking.slice(0, 6) ?? []);
      } else setSugg([]);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Não consegui carregar a galeria");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, surfaceId]);

  const projectCards: Card[] = useMemo(
    () =>
      project.map((m) => ({
        key: `sha:${m.sha256}`, name: m.filename, kind: m.kind, folder: "", duration: m.duration,
        width: m.width, height: m.height, thumb: api.mediaThumbUrl(m.sha256), pick: async () => m,
      })),
    [project],
  );
  const libraryCards: Card[] = useMemo(
    () =>
      library.map((it) => ({
        key: `lib:${it.id}`, name: it.name, kind: it.kind, folder: it.folder, duration: it.duration,
        width: it.width, height: it.height, thumb: api.libraryThumbUrl(it.id),
        pick: async () => (await api.importLibrary(it.id)).item,
      })),
    [library],
  );
  const byKey = useMemo(() => new Map([...projectCards, ...libraryCards].map((c) => [c.key, c])), [projectCards, libraryCards]);

  const shown = (tab === "project" ? projectCards : libraryCards).filter(
    (c) =>
      (kind === "all" || c.kind === kind) &&
      (!folder || c.folder === folder || c.folder.startsWith(folder + "/")) &&
      (!q || c.name.toLowerCase().includes(q.toLowerCase())),
  );

  const choose = async (c: Card) => {
    setBusy(c.key);
    try {
      onPick(await c.pick());
      onClose();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao importar");
    } finally {
      setBusy(null);
    }
  };

  if (!open) return null;
  return (
    <div className="gallery-backdrop" onClick={onClose}>
      <div className="gallery" role="dialog" aria-label="Galeria de mídias" onClick={(e) => e.stopPropagation()}>
        <div className="gallery-head">
          <h2>{title ?? "Escolher mídia"}</h2>
          <button className="btn btn-small" onClick={onClose}>Fechar</button>
        </div>

        {sugg.length > 0 && (
          <div className="gallery-sugg">
            <span className="dim small">⭐ Sugeridas para esta superfície</span>
            <div className="gallery-strip">
              {sugg.map((s) => {
                const c = byKey.get(s.ref);
                if (!c) return null;
                return (
                  <button key={s.ref} className="gcard gcard-sugg" title={s.reasons.join(" · ")} onClick={() => choose(c)} disabled={!!busy}>
                    <Thumb card={c} />
                    <span className="gname">{c.name}</span>
                    <span className="greason">{s.reasons[0]}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="gallery-tools">
          <div className="segmented">
            <button className={tab === "project" ? "on" : ""} onClick={() => setTab("project")}>No projeto ({project.length})</button>
            <button className={tab === "library" ? "on" : ""} onClick={() => setTab("library")}>Minhas pastas ({library.length})</button>
          </div>
          <input placeholder="Buscar pelo nome…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="segmented">
            {(["all", "video", "image", "gif"] as const).map((k) => (
              <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>
                {k === "all" ? "Tudo" : KIND_LABEL[k]}
              </button>
            ))}
          </div>
          {tab === "library" && folders.length > 1 && (
            <select value={folder} onChange={(e) => setFolder(e.target.value)} aria-label="Pasta">
              <option value="">Todas as pastas</option>
              {folders.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          )}
          {tab === "library" && (
            <button className="btn btn-small" onClick={() => load(true)} disabled={loading}>{loading ? "Lendo…" : "Reler pastas"}</button>
          )}
        </div>

        {tab === "library" && !hasRoots && (
          <p className="dim small gallery-empty">
            Nenhuma pasta configurada. No editor do PC, card <b>Biblioteca de mídias</b>, adicione a pasta do seu Google Drive
            (ex.: <code>G:\Meu Drive\Projeção</code>).
          </p>
        )}
        {shown.length === 0 && (tab === "project" || hasRoots) && (
          <p className="dim small gallery-empty">{loading ? "Carregando…" : "Nada por aqui com esses filtros."}</p>
        )}

        <div className="gallery-grid">
          {shown.map((c) => (
            <button key={c.key} className="gcard" onClick={() => choose(c)} disabled={!!busy} title={c.folder ? `${c.folder}/${c.name}` : c.name}>
              <Thumb card={c} />
              <span className="gname">{busy === c.key ? "Importando…" : c.name}</span>
              {c.folder && <span className="gfolder">{c.folder}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Thumb({ card }: { card: Card }) {
  const badge = card.kind === "video" && card.duration ? fmt(card.duration) : card.kind === "gif" ? "GIF" : "";
  return (
    <span className="gthumb">
      <img src={card.thumb} alt="" loading="lazy" />
      {badge && <span className="gbadge">{card.kind === "video" ? "▶ " : ""}{badge}</span>}
      {card.width > 0 && <span className="gres">{card.width}×{card.height}</span>}
    </span>
  );
}

function fmt(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}
