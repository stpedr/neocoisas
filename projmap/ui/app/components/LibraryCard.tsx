"use client";

// Pastas da galeria (só aparece no próprio mestre). Para o Google Drive: instale
// o "Google Drive para computador" e aponte para a pasta espelhada.

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";

export default function LibraryCard({ onError, onOk }: { onError: (m: string) => void; onOk: (m: string) => void }) {
  const [roots, setRoots] = useState<{ path: string; exists: boolean }[]>([]);
  const [count, setCount] = useState(0);
  const [canEdit, setCanEdit] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.library().then((l) => {
      setRoots(l.roots);
      setCount(l.items.length);
      setCanEdit(l.can_edit_roots);
    }).catch(() => setCanEdit(false));
  }, []);

  if (!canEdit) return null;

  const save = async (next: string[]) => {
    setBusy(true);
    try {
      const l = await api.setLibraryRoots(next);
      setRoots(l.roots);
      setCount(l.items.length);
      setDraft("");
      onOk(`Biblioteca: ${l.items.length} mídia(s) encontrada(s).`);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao salvar as pastas");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="card-head">
        <h2>Biblioteca de mídias</h2>
        <span className="dim small">{count} arquivo(s)</span>
      </div>
      <p className="dim small">
        Pastas do PC que aparecem na galeria. Para usar o <b>Google Drive</b>, instale o <i>Google Drive para computador</i> e
        adicione a pasta espelhada, ex.: <code>G:\Meu Drive\Projeção</code>. Só o que você escolher é copiado para o projeto.
      </p>
      {roots.map((r) => (
        <div key={r.path} className="row root-row">
          <span className={`root-path ${r.exists ? "" : "root-missing"}`} title={r.exists ? r.path : "pasta não encontrada"}>{r.path}</span>
          <button className="btn btn-small" disabled={busy} onClick={() => save(roots.filter((x) => x.path !== r.path).map((x) => x.path))}>Remover</button>
        </div>
      ))}
      <div className="row">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Colar o caminho da pasta" />
        <button className="btn btn-accent" disabled={busy || !draft.trim()} onClick={() => save([...roots.map((r) => r.path), draft.trim()])}>
          Adicionar
        </button>
      </div>
    </section>
  );
}
