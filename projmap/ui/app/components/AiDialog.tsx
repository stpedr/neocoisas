"use client";

// "Criar cena com IA": o texto vira uma cena interativa. A IA (LLM) só é usada
// aqui, quando o operador pede. Sem LLM configurado, monta por palavras-chave.

import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useEscape } from "../lib/interact";
import type { InteractState } from "../lib/types";

const EXAMPLES = [
  "5 fantasmas que param e cobrem o rosto quando eu olho, e vêm me buscar quando viro de costas",
  "vaga-lumes amarelos que vão para onde eu olho",
  "cardume de 20 peixes azuis que fogem de mim",
];

export default function AiDialog({ open, onClose, onDone, onError }: {
  open: boolean;
  onClose: () => void;
  onDone: (s: InteractState, msg: string) => void;
  onError: (m: string) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  useEscape(open, onClose);
  if (!open) return null;

  const generate = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const res = await api.interactGenerate(text, true);
      const notes = (res.notes ?? []).filter((n) => !n.includes("palavras-chave"));
      onDone(res, (res.source === "llm" ? "Cena criada pela IA." : "Cena montada por palavras-chave (IA indisponível).") +
        (notes.length ? ` ${notes.join(". ")}.` : ""));
      onClose();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao gerar a cena");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gallery-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label="Criar cena com IA" onClick={(e) => e.stopPropagation()}>
        <div className="gallery-head">
          <h2>✨ Criar cena com IA</h2>
          <button className="btn btn-small" onClick={onClose}>Fechar</button>
        </div>
        <p className="dim small">Descreva o que deve aparecer e como reage ao público. A cena entra nas superfícies com a fonte “Cena interativa”.</p>
        <textarea rows={4} autoFocus value={text} placeholder={EXAMPLES[0]} onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void generate(); }} />
        <div className="upload-row">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="btn btn-small" onClick={() => setText(ex)} title={ex}>
              {ex.split(" ").slice(0, 3).join(" ")}…
            </button>
          ))}
        </div>
        <button className="btn btn-accent btn-block" disabled={busy || !text.trim()} onClick={generate}>
          {busy ? "Gerando…" : "Gerar cena"}
        </button>
      </div>
    </div>
  );
}
