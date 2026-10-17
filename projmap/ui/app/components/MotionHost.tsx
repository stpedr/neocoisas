"use client";

// Host dos motions projetados: não é uma tela para pessoas. O Chromium headless
// do mestre abre /motion-host/; a lógica fica em lib/motionHost.ts.

import { useEffect, useRef, useState } from "react";
import { MotionHostController, unpackPacket, type HostFrame } from "../lib/motionHost";

function socketUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/motion-host`;
}

export default function MotionHost() {
  const [frames, setFrames] = useState<HostFrame[]>([]);
  const ctrlRef = useRef<MotionHostController | null>(null);
  const iframes = useRef(new Map<string, HTMLIFrameElement>());

  useEffect(() => {
    let closed = false;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    // Diagnóstico: quadros recebidos dos motions e custo de ler+enviar, a cada 2 s para o mestre.
    const stats = { frames: 0, ms: 0, start: performance.now() };

    // Um controlador só: numa reconexão os iframes (e as janelas deles) continuam valendo.
    const ctrl = new MotionHostController({
      socket: { send: () => {} },
      fetchHtml: async (url) => {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status} em ${url}`);
        return r.text();
      },
      onChange: () => setFrames([...ctrl.frames]),
    });
    ctrlRef.current = ctrl;

    const connect = () => {
      const sock = new WebSocket(socketUrl());
      ws = sock;
      sock.binaryType = "arraybuffer";
      ctrl.setSocket({
        send: (d) => sock.readyState === 1 && sock.send(d),
        get bufferedAmount() {
          return sock.bufferedAmount;
        },
      });
      sock.onmessage = (e: MessageEvent) => {
        if (typeof e.data === "string") {
          ctrl.handleText(e.data).catch((err: unknown) => console.error("motion-host:", err));
          return;
        }
        const { header, body } = unpackPacket(e.data as ArrayBuffer);
        if (header.kind !== "video" || typeof header.device !== "string") return;
        const device = header.device;
        createImageBitmap(new Blob([body], { type: "image/jpeg" }))
          .then((bmp) => {
            ctrl.deliverVideo(device, () => {
              // cada iframe recebe a sua cópia (o ImageBitmap é transferido)
              const c = new OffscreenCanvas(bmp.width, bmp.height);
              c.getContext("2d")?.drawImage(bmp, 0, 0);
              return c.transferToImageBitmap();
            });
            bmp.close();
          })
          .catch((err: unknown) => console.error("motion-host: vídeo", err));
      };
      sock.onclose = () => {
        if (!closed) retry = setTimeout(connect, 1000);
      };
    };

    const onMessage = (e: MessageEvent) => {
      const data = e.data as { type?: string; w?: number; h?: number; jpeg?: ArrayBuffer } | null;
      if (!data || data.type !== "projmap:frame" || !(data.jpeg instanceof ArrayBuffer)) return;
      const sid = ctrl.sidFor(e.source);
      if (!sid) {
        (e.source as Window | null)?.postMessage({ type: "projmap:ack" }, "*"); // nunca deixa o shim travado
        return;
      }
      const t0 = performance.now();
      if (ctrl.sendFrame(sid, new Uint8Array(data.jpeg), "jpeg", [data.w ?? 0, data.h ?? 0])) {
        stats.frames += 1;
        stats.ms += performance.now() - t0;
      }
      ctrl.ack(sid);
    };
    const statsTimer = setInterval(() => {
      const secs = (performance.now() - stats.start) / 1000;
      const fps = stats.frames / secs;
      const msPerFrame = stats.frames ? stats.ms / stats.frames : 0;
      if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({ type: "stats", fps: Math.round(fps * 10) / 10, ms: Math.round(msPerFrame * 10) / 10,
          buffered: ws.bufferedAmount }));
      }
      stats.frames = 0;
      stats.ms = 0;
      stats.start = performance.now();
    }, 2000);

    window.addEventListener("message", onMessage);
    connect();
    return () => {
      closed = true;
      clearInterval(statsTimer);
      if (retry) clearTimeout(retry);
      window.removeEventListener("message", onMessage);
      ws?.close();
    };
  }, []);

  return (
    <div style={{ position: "fixed", inset: 0, background: "#000", overflow: "hidden" }}>
      {frames.map((f) =>
        f.srcdoc === null ? null : (
          <iframe
            key={`${f.sid}:${f.media}`}
            title={`motion ${f.sid}`}
            sandbox="allow-scripts"
            srcDoc={f.srcdoc}
            ref={(el) => {
              if (el) iframes.current.set(f.sid, el);
              else iframes.current.delete(f.sid);
              ctrlRef.current?.attach(f.sid, el?.contentWindow ?? null);
            }}
            onLoad={(e) => {
              ctrlRef.current?.attach(f.sid, e.currentTarget.contentWindow);
              ctrlRef.current?.loaded(f.sid);
            }}
            style={{ position: "absolute", left: 0, top: 0, width: `${f.w}px`, height: `${f.h}px`, border: 0, background: "#000" }}
          />
        ),
      )}
    </div>
  );
}
