"use client";

// Estado ao vivo da camada interativa, compartilhado pelo editor (gaveta
// Interação, widget do celular). "off" = mestre sem a camada (--no-interact):
// aí nada de interação aparece na tela.

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { InteractState } from "./types";

export function useInteract(pollMs = 500) {
  const [st, setSt] = useState<InteractState | null>(null);
  const [off, setOff] = useState<boolean | null>(null); // null = ainda não sei
  const [caught, setCaught] = useState(false);
  const lastCaught = useRef(0);

  useEffect(() => {
    let alive = true;
    let timer = 0;
    const poll = async () => {
      try {
        const s = await api.interactState();
        if (!alive) return;
        setSt(s);
        setOff(false);
        const c = s.events.filter((e) => e.name === "caught").at(-1);
        if (c && c.t !== lastCaught.current) {
          lastCaught.current = c.t;
          setCaught(true);
          window.setTimeout(() => setCaught(false), 1200);
        }
      } catch (e) {
        if (alive && e instanceof ApiError && e.status === 404) {
          setOff(true);
          return; // desligada: não fica perguntando
        }
      }
      if (alive) timer = window.setTimeout(poll, pollMs);
    };
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [pollMs]);

  return { st, setSt, off, caught };
}

/** Fecha diálogos com Esc. */
export function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
}
