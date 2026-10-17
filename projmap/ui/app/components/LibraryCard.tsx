"use client";

// Pastas do PC na galeria (só no próprio mestre). Para o Drive sem configurar
// API: instale o "Google Drive para computador" e aponte para a pasta espelhada.

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

export default function LibraryCard({
  onError,
  onOk,
}: {
  onError: (m: string) => void;
  onOk: (m: string) => void;
}) {
  const [roots, setRoots] = useState<{ path: string; exists: boolean }[]>([]);
  const [count, setCount] = useState(0);
  const [canEdit, setCanEdit] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .library()
      .then((l) => {
        setRoots(l.roots);
        setCount(l.items.length);
        setCanEdit(l.can_edit_roots);
      })
      .catch(() => setCanEdit(false));
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
    <div className="folder-manager">
      <div className="card-head">
        <b className="small">Pastas do computador</b>
        <span className="dim small">{count} arquivo(s)</span>
      </div>
      <p className="dim small">
        Aparecem em <b>Minhas pastas</b>. Pode ser a pasta do <i>Google Drive para computador</i> (ex.:{" "}
        <code>G:\Meu Drive\Projeção</code>). Só o que você escolher é copiado para o projeto.
      </p>
      {roots.map((r) => (
        <div key={r.path} className="row root-row">
          <span
            className={`root-path ${r.exists ? "" : "root-missing"}`}
            title={r.exists ? r.path : "pasta não encontrada"}
          >
            {r.path}
          </span>
          <Button
            size="sm"
            disabled={busy}
            onClick={() => save(roots.filter((x) => x.path !== r.path).map((x) => x.path))}
          >
            Remover
          </Button>
        </div>
      ))}
      <div className="row">
        <Input
          className="flex-1"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Colar o caminho da pasta"
        />
        <Button
          variant="primary"
          disabled={busy || !draft.trim()}
          onClick={() => save([...roots.map((r) => r.path), draft.trim()])}
        >
          Adicionar
        </Button>
      </div>
    </div>
  );
}
