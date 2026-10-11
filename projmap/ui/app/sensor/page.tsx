"use client";

// Página do CELULAR-SENSOR (substitui o Kinect).
//
// Montagem: celular na parede projetada, apontado para o público, ligado ao PC
// por USB com `adb reverse tcp:8100 tcp:8100` (ou `--adb` no mestre). Assim esta
// página abre em http://localhost:8100/sensor/ — localhost é contexto seguro, então
// a câmera funciona sem HTTPS — e os dados vão pelo cabo.
//
// O celular roda a rede neural do rosto (MediaPipe FaceLandmarker, no navegador) e
// manda ao PC só 6 pontos do rosto (~20×/s). O PC calcula posição e rotação da
// cabeça (solvePnP, mesma função testada da webcam) e alimenta a cena interativa.

import { useEffect, useRef, useState } from "react";
import { API_BASE, withToken } from "../lib/api";

// Mesmos índices de projmap/interact/sensors.py (FACE_LANDMARKS):
// nariz, queixo, olho esq., olho dir., boca esq., boca dir.
const FACE_POINTS = [1, 152, 263, 33, 291, 61];
const SEND_HZ = 20;
const REMOTE_MODEL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

type Phase = "idle" | "loading" | "running" | "error";
interface Feedback {
  tracked: boolean;
  watching: boolean;
  yaw_deg: number;
  x: number;
  scene: string;
  moving: number;
  frozen: number;
}

export default function SensorPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const stopRef = useRef<() => void>(() => {});
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [mirror, setMirror] = useState(true);
  const mirrorRef = useRef(true);
  const [face, setFace] = useState(false);
  const [fps, setFps] = useState(0);
  const [wsOk, setWsOk] = useState(false);
  const [fb, setFb] = useState<Feedback | null>(null);
  const [secure, setSecure] = useState(true);

  useEffect(() => {
    setSecure(window.isSecureContext);
    return () => stopRef.current();
  }, []);
  useEffect(() => {
    mirrorRef.current = mirror;
  }, [mirror]);

  // ---- WebSocket com reconexão
  function connect() {
    const base = API_BASE || window.location.origin;
    const url = withToken(base.replace(/^http/, "ws") + "/api/interact/phone");
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setWsOk(true);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.error) setError(data.error);
        else setFb(data);
      } catch {
        /* ignora */
      }
    };
    ws.onclose = () => {
      setWsOk(false);
      if (wsRef.current === ws) window.setTimeout(connect, 1000);
    };
  }

  async function modelPath(): Promise<string> {
    try {
      const r = await fetch(`${API_BASE}/api/interact/face-model`, { method: "HEAD" });
      if (r.ok) return `${API_BASE}/api/interact/face-model`;
    } catch {
      /* sem modelo local */
    }
    return REMOTE_MODEL; // precisa de internet no celular
  }

  async function start() {
    setPhase("loading");
    setError("");
    try {
      const { FilesetResolver, FaceLandmarker } = await import("@mediapipe/tasks-vision");
      const fileset = await FilesetResolver.forVisionTasks(`${API_BASE}/mediapipe/wasm`);
      const model = await modelPath();
      let landmarker;
      try {
        landmarker = await FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: model, delegate: "GPU" },
          runningMode: "VIDEO",
          numFaces: 1,
        });
      } catch {
        landmarker = await FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: model, delegate: "CPU" },
          runningMode: "VIDEO",
          numFaces: 1,
        });
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: facing, width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play();

      // Tela sempre ligada (o celular fica preso na parede).
      let wake: { release: () => Promise<void> } | null = null;
      try {
        wake = await (navigator as unknown as { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void> }> } }).wakeLock?.request("screen") ?? null;
      } catch {
        /* sem wake lock: ok */
      }

      connect();
      setPhase("running");

      let running = true;
      let lastSend = 0;
      let frames = 0;
      let fpsT0 = performance.now();
      let lastFps = 0;
      const loop = () => {
        if (!running) return;
        const now = performance.now();
        if (video.readyState >= 2) {
          const res = landmarker.detectForVideo(video, now);
          const lm = res.faceLandmarks?.[0];
          frames++;
          if (now - fpsT0 > 1000) {
            lastFps = (frames * 1000) / (now - fpsT0);
            setFps(Math.round(lastFps));
            frames = 0;
            fpsT0 = now;
          }
          setFace(!!lm);
          draw(lm ? FACE_POINTS.map((i) => [lm[i].x, lm[i].y]) : null);
          const ws = wsRef.current;
          if (ws && ws.readyState === WebSocket.OPEN && now - lastSend >= 1000 / SEND_HZ) {
            lastSend = now;
            ws.send(
              JSON.stringify({
                face: !!lm,
                pts: lm ? FACE_POINTS.map((i) => [lm[i].x, lm[i].y]) : [],
                w: video.videoWidth,
                h: video.videoHeight,
                mirror: mirrorRef.current,
                fps: lastFps,
              }),
            );
          }
        }
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);

      stopRef.current = () => {
        running = false;
        stream.getTracks().forEach((t) => t.stop());
        landmarker.close();
        const ws = wsRef.current;
        wsRef.current = null;
        ws?.close();
        void wake?.release();
      };
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function draw(pts: number[][] | null) {
    const cv = canvasRef.current;
    const video = videoRef.current;
    if (!cv || !video) return;
    cv.width = video.videoWidth;
    cv.height = video.videoHeight;
    const g = cv.getContext("2d");
    if (!g) return;
    g.clearRect(0, 0, cv.width, cv.height);
    if (!pts) return;
    g.fillStyle = "#34d399";
    for (const [x, y] of pts) {
      g.beginPath();
      g.arc(x * cv.width, y * cv.height, 5, 0, Math.PI * 2);
      g.fill();
    }
  }

  const stop = () => {
    stopRef.current();
    stopRef.current = () => {};
    setPhase("idle");
    setFace(false);
  };

  return (
    <main className="sensor">
      <header className="sensor-head">
        <span className="logo" aria-hidden>◆</span>
        <b>ProjMap · celular-sensor</b>
        <span className={`dot-status ${wsOk ? "ok" : ""}`}>{wsOk ? "PC conectado" : "sem PC"}</span>
      </header>

      {!secure && (
        <div className="sensor-warn">
          Este endereço não é seguro para a câmera. Ligue o celular por USB com ADB e abra
          <code> http://localhost:8100/sensor/</code> (o mestre faz isso com <code>--adb</code>).
        </div>
      )}

      <div className={`sensor-view ${facing === "user" ? "selfie" : ""}`}>
        <video ref={videoRef} playsInline muted />
        <canvas ref={canvasRef} />
        {phase !== "running" && (
          <div className="sensor-placeholder">
            {phase === "loading" ? "Carregando detecção de rosto…" : "Câmera desligada"}
          </div>
        )}
      </div>

      <section className="sensor-status" aria-live="polite">
        <div className={`big ${face ? "ok" : "warn"}`}>{face ? "Rosto detectado" : "Sem rosto (de costas?)"}</div>
        {fb && (
          <>
            <div>
              PC vê: <b>{!fb.tracked ? "ninguém" : fb.watching ? "olhando a parede" : "de costas"}</b> · cabeça{" "}
              {Math.round(fb.yaw_deg)}° · posição {Math.round(fb.x * 100)}%
            </div>
            <div className="dim">
              {fb.scene}: {fb.moving} em movimento · {fb.frozen} parados
            </div>
          </>
        )}
        <div className="dim">{fps} fps no celular</div>
        {error && <div className="err">{error}</div>}
      </section>

      <section className="sensor-controls">
        {phase === "running" ? (
          <button className="btn btn-danger btn-block" onClick={stop}>
            Parar
          </button>
        ) : (
          <button className="btn btn-accent btn-block" onClick={start} disabled={phase === "loading"}>
            Iniciar sensor
          </button>
        )}
        <div className="row">
          <label className="toggle">
            <input
              type="radio"
              name="cam"
              checked={facing === "environment"}
              disabled={phase === "running"}
              onChange={() => setFacing("environment")}
            />
            Câmera traseira
          </label>
          <label className="toggle">
            <input type="radio" name="cam" checked={facing === "user"} disabled={phase === "running"} onChange={() => setFacing("user")} />
            Frontal
          </label>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={mirror} onChange={(e) => setMirror(e.target.checked)} />
          Celular na parede olhando o público (inverte esquerda/direita)
        </label>
        <p className="dim small">
          Prenda o celular na parede projetada, na altura dos olhos, com a câmera virada para quem vai jogar. Deixe-o
          carregando pelo USB.
        </p>
      </section>
    </main>
  );
}
