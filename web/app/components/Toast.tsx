"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

type ToastType = "info" | "ok" | "error";
type ToastItem = { id: number; msg: string; type: ToastType };

const ToastCtx = createContext<(msg: string, type?: ToastType) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((msg: string, type: ToastType = "info") => {
    if (!msg) return;
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, msg, type }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 4500);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="true">
        {items.map((i) => (
          <div key={i.id} className={`toast ${i.type}`} role="status">
            {i.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/** Skeleton reutilizável para estados de carregamento. */
export function Skeleton({
  height = 16,
  width = "100%",
  style,
}: {
  height?: number | string;
  width?: number | string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className="skeleton"
      style={{ height, width, marginBottom: 8, ...style }}
      aria-hidden
    />
  );
}
