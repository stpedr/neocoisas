"use client";

// "Sugerir mídias": uma proposta por superfície (sem repetir mídia se der),
// com o motivo. O operador desmarca o que não quer e aplica de uma vez.

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { MediaItem, Suggestion, Surface } from "../lib/types";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";

interface Props {
  open: boolean;
  surfaces: Surface[];
  onApply: (picks: { surfaceId: string; item: MediaItem }[]) => void;
  onClose: () => void;
  onError: (m: string) => void;
}

export default function SuggestAll({ open, surfaces, onApply, onClose, onError }: Props) {
  const [picks, setPicks] = useState<Record<string, Suggestion | null>>({});
  const [on, setOn] = useState<Set<string>>(new Set());
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api
      .suggest(surfaces.map((s) => s.id))
      .then((r) => {
        const p: Record<string, Suggestion | null> = {};
        for (const s of surfaces) p[s.id] = r.suggestions[s.id]?.pick ?? null;
        setPicks(p);
        setOn(new Set(Object.keys(p).filter((k) => p[k])));
        setCount(r.media_count);
      })
      .catch((e) => onError(e instanceof ApiError ? e.message : "Falha ao sugerir"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const thumb = (ref: string) =>
    ref.startsWith("lib:") ? api.libraryThumbUrl(ref.slice(4)) : api.mediaThumbUrl(ref.slice(4));

  const apply = async () => {
    setBusy(true);
    try {
      const out: { surfaceId: string; item: MediaItem }[] = [];
      const cache = new Map<string, MediaItem>();
      const info = (await api.mediaInfo()).items;
      for (const sid of on) {
        const s = picks[sid];
        if (!s) continue;
        let item = cache.get(s.ref);
        if (!item) {
          item = s.ref.startsWith("lib:")
            ? (await api.importLibrary(s.ref.slice(4))).item
            : info.find((m) => m.sha256 === s.ref.slice(4));
          if (item) cache.set(s.ref, item);
        }
        if (item) out.push({ surfaceId: sid, item });
      }
      onApply(out);
      onClose();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao aplicar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent aria-label="Sugestões de mídia">
        <DialogHeader>
          <DialogTitle>Sugestões de mídia</DialogTitle>
          <Button size="sm" onClick={onClose}>
            Fechar
          </Button>
        </DialogHeader>
        <p className="dim small">
          Escolhidas entre {count} mídia(s) do projeto e das suas pastas, pelo formato e pela resolução de cada superfície.
          Desmarque o que não quiser.
        </p>
        <ul className="sugg-list">
          {surfaces.map((s) => {
            const p = picks[s.id];
            return (
              <li key={s.id}>
                <label className="toggle">
                  <Checkbox
                    disabled={!p}
                    checked={on.has(s.id)}
                    onCheckedChange={() =>
                      setOn((cur) => {
                        const n = new Set(cur);
                        if (n.has(s.id)) n.delete(s.id);
                        else n.add(s.id);
                        return n;
                      })
                    }
                  />
                  <b>{s.label || s.id}</b>
                </label>
                {p ? (
                  <span className="sugg-pick">
                    <img src={thumb(p.ref)} alt="" />
                    <span>
                      {p.name}
                      <span className="dim small"> · {p.reasons.join(" · ")}</span>
                    </span>
                  </span>
                ) : (
                  <span className="dim small">sem mídia disponível</span>
                )}
              </li>
            );
          })}
        </ul>
        <Button variant="primary" size="block" disabled={busy || on.size === 0} onClick={apply}>
          {busy ? "Aplicando…" : `Aplicar em ${on.size} superfície(s)`}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
