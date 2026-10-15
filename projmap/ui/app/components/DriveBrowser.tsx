"use client";

// Aba "Google Drive" da galeria: navega a pasta do Drive (subpastas com GIFs,
// vídeos…) e importa o arquivo escolhido para o projeto. A conexão é feita no
// próprio mestre (OAuth, botão "Conectar") ou com chave de API + pasta pública.

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { DriveEntry, DriveListing, DriveStatus, MediaItem, MediaKind } from "../lib/types";

export default function DriveBrowser({ kind, q, busy, onPick, onError }: {
  kind: MediaKind | "all";
  q: string;
  busy: string | null;
  onPick: (key: string, pick: () => Promise<MediaItem>) => void;
  onError: (m: string) => void;
}) {
  const [status, setStatus] = useState<DriveStatus | null>(null);
  const [trail, setTrail] = useState<{ id: string; name: string }[]>([]);
  const [listing, setListing] = useState<DriveListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [link, setLink] = useState("");
  const [editing, setEditing] = useState(false);

  const open = async (folder?: { id: string; name: string }, reset = false) => {
    setLoading(true);
    try {
      const l = await api.driveList(folder?.id);
      setListing(l);
      setTrail((t) => {
        if (reset || !folder) return [l.folder];
        const i = t.findIndex((x) => x.id === l.folder.id);
        return i >= 0 ? t.slice(0, i + 1) : [...t, l.folder];
      });
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Não consegui abrir a pasta do Drive");
    } finally {
      setLoading(false);
    }
  };

  const refreshStatus = async () => {
    try {
      const s = await api.driveStatus();
      setStatus(s);
      if (s.connected && s.root) await open(undefined, true);
    } catch {
      setStatus(null);
    }
  };

  useEffect(() => {
    void refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveFolder = async () => {
    try {
      const s = await api.driveSetFolder(link.trim());
      setStatus(s);
      setEditing(false);
      setLink("");
      if (s.connected && s.root) await open(undefined, true);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Link de pasta inválido");
    }
  };

  if (!status) return <p className="dim small gallery-empty">Verificando o Google Drive…</p>;

  if (!status.configured) {
    return (
      <div className="drive-setup">
        <p className="small"><b>Ligar o Google Drive</b> (uma vez, no computador do mestre):</p>
        <ol className="small">
          <li>No Google Cloud, ative a <i>Google Drive API</i> e crie um cliente OAuth do tipo <i>App para computador</i>.</li>
          <li>No arquivo <code>.env</code> da pasta do ProjMap, preencha <code>PROJMAP_GDRIVE_CLIENT_ID</code> e <code>PROJMAP_GDRIVE_CLIENT_SECRET</code>.</li>
          <li>Reabra o ProjMap e clique em <b>Conectar Google Drive</b> aqui.</li>
        </ol>
        <p className="dim small">
          Sem login: use <code>PROJMAP_GDRIVE_API_KEY</code> com a pasta compartilhada como “qualquer pessoa com o link”.
          Detalhes no GUIA. Alternativa sem configurar nada: o <i>Google Drive para computador</i> + aba <b>Minhas pastas</b>.
        </p>
      </div>
    );
  }

  const folderForm = status.can_configure && (editing || (!status.folder_set && status.mode === "apikey")) && (
    <div className="row">
      <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Cole o link da pasta do Drive (drive.google.com/drive/folders/…)"
             onKeyDown={(e) => e.key === "Enter" && saveFolder()} />
      <button className="btn btn-small btn-accent" disabled={status.mode === "apikey" && !link.trim()} onClick={saveFolder}>Usar pasta</button>
      {editing && <button className="btn btn-small" onClick={() => setEditing(false)}>Cancelar</button>}
    </div>
  );

  if (status.mode === "oauth" && !status.connected) {
    return (
      <div className="drive-setup">
        {status.can_configure ? (
          <>
            <p className="small">Conecte sua conta para ver as pastas do Drive aqui (acesso só de leitura).</p>
            <a className="btn btn-accent" href={api.driveConnectUrl()}>Conectar Google Drive</a>
          </>
        ) : (
          <p className="dim small">O Google Drive ainda não foi conectado. Conecte pelo editor no computador do mestre.</p>
        )}
      </div>
    );
  }

  const match = (e: DriveEntry) => (kind === "all" || e.kind === kind) && (!q || e.name.toLowerCase().includes(q.toLowerCase()));
  const folders = (listing?.folders ?? []).filter((f) => !q || f.name.toLowerCase().includes(q.toLowerCase()));
  const items = (listing?.items ?? []).filter(match);

  return (
    <div className="drive">
      <div className="drive-bar">
        <nav className="crumbs" aria-label="Pastas do Drive">
          {trail.map((f, i) => (
            <span key={f.id}>
              {i > 0 && <span className="dim"> / </span>}
              <button className="crumb" disabled={i === trail.length - 1 || loading} onClick={() => open(f)}>{i === 0 ? `☁ ${f.name}` : f.name}</button>
            </span>
          ))}
        </nav>
        <div className="row">
          <button className="btn btn-small" disabled={loading} onClick={() => trail.length && open(trail[trail.length - 1])}>
            {loading ? "Lendo…" : "Atualizar"}
          </button>
          {status.can_configure && !editing && (
            <button className="btn btn-small" onClick={() => setEditing(true)} title="Escolher outra pasta raiz">Trocar pasta</button>
          )}
          {status.can_configure && status.mode === "oauth" && (
            <button className="btn btn-small" onClick={async () => setStatus(await api.driveDisconnect())}>Desconectar</button>
          )}
        </div>
      </div>
      {folderForm}

      {status.root && (
        <>
          {folders.length > 0 && (
            <div className="folder-grid">
              {folders.map((f) => (
                <button key={f.id} className="folder-tile" disabled={loading} onClick={() => open({ id: f.id, name: f.name })}>
                  <span aria-hidden>📁</span> {f.name}
                </button>
              ))}
            </div>
          )}
          {!loading && listing && items.length === 0 && folders.length === 0 && (
            <p className="dim small gallery-empty">Nenhuma mídia (vídeo, GIF ou imagem) nesta pasta{q || kind !== "all" ? " com esses filtros" : ""}.</p>
          )}
          <div className="gallery-grid">
            {items.map((it) => {
              const key = `drive:${it.id}`;
              return (
                <button key={it.id} className="gcard" disabled={!!busy} title={it.name}
                        onClick={() => onPick(key, async () => (await api.driveImport(it.id)).item)}>
                  <span className="gthumb">
                    {it.has_thumb || it.kind !== "video" ? <img src={api.driveThumbUrl(it.id)} alt="" loading="lazy" /> : <span className="gicon">🎞</span>}
                    {it.kind === "video" && it.duration > 0 && <span className="gbadge">▶ {fmt(it.duration)}</span>}
                    {it.kind === "gif" && <span className="gbadge">GIF</span>}
                    {it.width > 0 && <span className="gres">{it.width}×{it.height}</span>}
                  </span>
                  <span className="gname">{busy === key ? "Baixando do Drive…" : it.name}</span>
                  <span className="gfolder">{mb(it.size_bytes)}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function fmt(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

function mb(b: number) {
  return b ? (b >= 1 << 20 ? `${(b / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`) : "";
}
