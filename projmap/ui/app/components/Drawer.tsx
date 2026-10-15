"use client";

// Gaveta do painel lateral: título clicável que abre/fecha o conteúdo.
// O estado (aberta/fechada) fica salvo por gaveta no navegador. Os botões da
// barra de atalhos abrem uma gaveta e rolam até ela com `openDrawer(id)`.

import { useEffect, useRef, useState, type ReactNode } from "react";

const KEY = "projmap.drawer.";
const EVENT = "projmap:drawer";

export function openDrawer(id: string) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: id }));
}

function load(id: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(KEY + id);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

function store(id: string, open: boolean) {
  try {
    localStorage.setItem(KEY + id, open ? "1" : "0");
  } catch {
    /* navegação privada: só não lembra */
  }
}

interface Props {
  id: string;
  title: string;
  icon?: string;
  badge?: ReactNode;
  actions?: ReactNode; // botões no cabeçalho (não abrem/fecham a gaveta)
  defaultOpen?: boolean;
  alert?: boolean;
  children: ReactNode;
}

export default function Drawer({ id, title, icon, badge, actions, defaultOpen = false, alert = false, children }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => setOpen(load(id, defaultOpen)), [id, defaultOpen]);

  useEffect(() => {
    const onOpen = (e: Event) => {
      if ((e as CustomEvent<string>).detail !== id) return;
      setOpen(true);
      store(id, true);
      window.setTimeout(() => ref.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 30);
    };
    window.addEventListener(EVENT, onOpen);
    return () => window.removeEventListener(EVENT, onOpen);
  }, [id]);

  const toggle = () => {
    setOpen((o) => {
      store(id, !o);
      return !o;
    });
  };

  return (
    <section ref={ref} className={`drawer ${open ? "drawer-open" : ""} ${alert ? "card-alert" : ""}`} id={`drawer-${id}`}>
      <div className="drawer-head">
        <button className="drawer-toggle" aria-expanded={open} onClick={toggle}>
          <span className="drawer-chevron" aria-hidden>▸</span>
          {icon && <span className="drawer-icon" aria-hidden>{icon}</span>}
          <span className="drawer-title">{title}</span>
          {badge !== undefined && badge !== null && <span className="drawer-badge">{badge}</span>}
        </button>
        {actions && <div className="drawer-actions">{actions}</div>}
      </div>
      {open && <div className="drawer-body">{children}</div>}
    </section>
  );
}
