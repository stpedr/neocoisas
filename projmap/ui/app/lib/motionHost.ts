// Página host dos motions projetados (roda no Chromium headless dedicado do mestre,
// ver projmap/motion/). Cada sessão aberta pelo renderer vira um iframe sandbox
// ("allow-scripts", origem opaca: o motion não alcança a API). Um shim injetado no
// motion captura o maior <canvas> logo depois de cada requestAnimationFrame e manda
// um ImageBitmap para cá; a página lê os pixels e envia ao mestre pelo WebSocket.
//
// Protocolo binário (igual a projmap/motion/hub.py): uint32 LE com o tamanho do
// cabeçalho JSON + cabeçalho + corpo.

import type { MotionAudioFrame } from "./motionModule";

export type JsonHeader = Record<string, string | number | boolean | null>;

export function packPacket(header: JsonHeader, body: Uint8Array | Uint8ClampedArray): ArrayBuffer {
  const head = new TextEncoder().encode(JSON.stringify(header));
  const buf = new ArrayBuffer(4 + head.length + body.length);
  new DataView(buf).setUint32(0, head.length, true);
  const bytes = new Uint8Array(buf);
  bytes.set(head, 4);
  bytes.set(body, 4 + head.length);
  return buf;
}

export function unpackPacket(buf: ArrayBuffer): { header: JsonHeader; body: Uint8Array } {
  if (buf.byteLength < 4) throw new Error("pacote curto");
  const n = new DataView(buf).getUint32(0, true);
  if (n > 4096 || 4 + n > buf.byteLength) throw new Error("cabeçalho inválido");
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n))) as JsonHeader;
  return { header, body: new Uint8Array(buf, 4 + n) };
}

/** Script que roda dentro do iframe do motion, antes do código dele.
 *
 * O rAF do motion é cadenciado aqui a ~60 Hz (o navegador dedicado roda sem limite de
 * frame rate, porque o agendador do headless é instável).
 *
 * Logo depois de cada requestAnimationFrame do motion (ainda no mesmo quadro, com o
 * buffer do WebGL desenhado) ele codifica o maior <canvas> em JPEG (``toBlob`` roda
 * fora da thread principal) e manda só os bytes para a página host. Um quadro por vez
 * (dois em voo foi medido pior: disputa a GPU com o projetor); o ``projmap:ack`` libera
 * o próximo, e um ack perdido expira em 1 s. */
function shimSource(fps: number): string {
  return `<script>(function(){
var P=window.parent,busy=0,since=0,last=0,lastRaf=0,MIN=1000 / ${fps}-2,raf=window.requestAnimationFrame.bind(window);
function pick(){var cs=document.getElementsByTagName("canvas"),best=null,a=0;for(var i=0;i<cs.length;i++){var s=cs[i].width*cs[i].height;if(s>a){a=s;best=cs[i];}}return best;}
function done(){busy=Math.max(0,busy-1);}
function grab(){var now=performance.now();if(busy>0&&now-since>1000)busy=0;if(busy>=1||now-last<MIN)return;var c=pick();if(!c||!c.width||!c.height)return;last=now;if(busy===0)since=now;busy++;var w=c.width,h=c.height;
try{c.toBlob(function(b){if(!b){done();return;}b.arrayBuffer().then(function(buf){P.postMessage({type:"projmap:frame",w:w,h:h,jpeg:buf},"*",[buf]);},done);},"image/jpeg",0.85);}catch(e){done();}}
var FRAME=1000/60,nextAt=0;
window.requestAnimationFrame=function(cb){var wait=Math.max(0,nextAt-performance.now());
var run=function(){return raf(function(t){nextAt=Math.max(nextAt+FRAME,performance.now());try{cb(t);}finally{lastRaf=performance.now();grab();}});};
if(wait<1)return run();setTimeout(run,wait);return 0;};
setInterval(function(){if(performance.now()-lastRaf>500)grab();},1000 / ${fps});
window.addEventListener("message",function(e){if(e.source===P&&e.data&&e.data.type==="projmap:ack"){done();since=performance.now();}});
})();</script>`;
}

export function buildSrcdoc(html: string, fps = 30): string {
  const shim = shimSource(fps);
  const m = /<head\b[^>]*>/i.exec(html);
  if (!m) return shim + html;
  const at = m.index + m[0].length;
  return html.slice(0, at) + shim + html.slice(at);
}

// ------------------------------------------------------------------ áudio
export interface MasterLevels {
  bass: number;
  mid: number;
  high: number;
  level: number;
  beat: number; // envelope de batida do mestre (não usado como impulso)
  beats: number; // contador de batidas
}

export interface AudioState {
  beats: number;
  energy: number;
  lastT: number | null;
  beatTimes: number[];
  count: number;
}

export function createAudioState(): AudioState {
  return { beats: 0, energy: 0, lastT: null, beatTimes: [], count: 0 };
}

export type HostAudioPayload = Omit<MotionAudioFrame, "snare" | "hat">;

/** Níveis do mestre → payload de ``motion:audio`` (seção 6 da spec). */
export function audioPayload(st: AudioState, lv: MasterLevels, nowMs: number): HostAudioPayload {
  const dt = st.lastT === null ? 0 : Math.max(0, (nowMs - st.lastT) / 1000);
  st.lastT = nowMs;
  st.energy += (lv.level - st.energy) * Math.min(1, dt / 4); // média de ~4 s
  const hit = lv.beats > st.beats;
  let downbeat = 0;
  if (hit) {
    st.beats = lv.beats;
    st.count += 1;
    st.beatTimes = [...st.beatTimes, nowMs].slice(-9);
    if (st.count % 4 === 1) downbeat = 1;
  }
  let bpm = 0;
  let beatPhase = 0;
  let barPhase = 0;
  if (st.beatTimes.length >= 4) {
    const gaps = st.beatTimes.slice(1).map((t, i) => t - st.beatTimes[i]).sort((a, b) => a - b);
    const period = gaps[gaps.length >> 1];
    const est = 60000 / period;
    if (est >= 70 && est <= 180) {
      bpm = est;
      const since = nowMs - st.beatTimes[st.beatTimes.length - 1];
      beatPhase = Math.min(1, since / period);
      barPhase = (((st.count - 1) % 4) + beatPhase) / 4;
    }
  }
  const impulse = hit ? 1 : 0;
  return {
    bass: lv.bass,
    mid: lv.mid,
    high: lv.high,
    level: lv.level,
    energy: st.energy,
    kick: impulse,
    beat: impulse,
    downbeat,
    bpm,
    beatPhase,
    barPhase,
  };
}

// ------------------------------------------------------------------ controlador
export interface HostSession {
  sid: string;
  media: string;
  w: number;
  h: number;
  params: Record<string, string | number | boolean>;
  mode: string | null;
  device: string | null;
}

export interface HostFrame extends HostSession {
  srcdoc: string | null;
}

export interface HostSocket {
  send(data: string | ArrayBuffer): void;
  /** Bytes ainda na fila do WebSocket (``WebSocket.bufferedAmount``). */
  bufferedAmount?: number;
}

/** Acima disso o quadro novo é descartado: melhor pular um quadro que atrasar a parede. */
export const MAX_BUFFERED = 1_500_000;

export interface MotionWindow {
  postMessage(message: unknown, targetOrigin: string, transfer?: Transferable[]): void;
}

interface BitmapLike {
  width: number;
  height: number;
  close(): void;
}

interface Options {
  socket: HostSocket;
  fetchHtml: (url: string) => Promise<string>;
  onChange: () => void;
  fps?: number;
}

export class MotionHostController {
  frames: HostFrame[] = [];
  private html = new Map<string, string>();
  private wins = new Map<string, MotionWindow>();
  private audio = createAudioState();

  constructor(private opts: Options) {}

  /** Troca o WebSocket (reconexão) sem perder os iframes já ligados. */
  setSocket(socket: HostSocket) {
    this.opts = { ...this.opts, socket };
  }

  setSessions(sessions: HostSession[]) {
    this.frames = sessions.map((s) => ({ ...s, srcdoc: this.srcdocFor(s.media) }));
    const live = new Set(sessions.map((s) => s.sid));
    for (const sid of Array.from(this.wins.keys())) if (!live.has(sid)) this.wins.delete(sid);
    this.opts.onChange();
  }

  private srcdocFor(media: string): string | null {
    const html = this.html.get(media);
    return html === undefined ? null : buildSrcdoc(html, this.opts.fps ?? 30);
  }

  async handleText(text: string): Promise<void> {
    const msg = JSON.parse(text) as { type: string } & Record<string, unknown>;
    if (msg.type === "sessions") {
      const sessions = msg.sessions as HostSession[];
      this.setSessions(sessions);
      const missing = Array.from(new Set(sessions.map((s) => s.media))).filter((m) => !this.html.has(m));
      await Promise.all(missing.map(async (m) => this.html.set(m, await this.opts.fetchHtml(`/media/${m}`))));
      if (missing.length) this.setSessions(sessions);
    } else if (msg.type === "audio") {
      const payload = audioPayload(this.audio, msg as unknown as MasterLevels, performance.now());
      for (const win of Array.from(this.wins.values())) win.postMessage({ type: "motion:audio", payload }, "*");
    }
  }

  attach(sid: string, win: MotionWindow | null) {
    if (win) this.wins.set(sid, win);
    else this.wins.delete(sid);
  }

  loaded(sid: string) {
    const f = this.frames.find((x) => x.sid === sid);
    const win = this.wins.get(sid);
    if (!f || !win) return;
    const payload = { embed: true, params: f.params, mode: f.mode ?? undefined, audioSource: "external" };
    win.postMessage({ type: "motion:init", payload }, "*");
  }

  sidFor(source: unknown): string | null {
    for (const [sid, win] of Array.from(this.wins.entries())) if (win === source) return sid;
    return null;
  }

  /** Libera o shim do motion para capturar o próximo quadro. */
  ack(sid: string) {
    this.wins.get(sid)?.postMessage({ type: "projmap:ack" }, "*");
  }

  /** Quadro do motion (JPEG, ou RGBA w×h) → mestre. ``false`` = descartado (fila cheia ou sessão sumiu).
   * ``size``: tamanho real do canvas do motion (padrão: o da sessão). */
  sendFrame(sid: string, body: Uint8Array | Uint8ClampedArray, fmt: "jpeg" | "rgba", size?: [number, number]): boolean {
    const f = this.frames.find((x) => x.sid === sid);
    if (!f) return false;
    const [w, h] = size ?? [f.w, f.h];
    if (fmt === "rgba" && body.length !== w * h * 4) return false;
    if ((this.opts.socket.bufferedAmount ?? 0) > MAX_BUFFERED) return false;
    this.opts.socket.send(packPacket({ sid, w, h, fmt }, body));
    return true;
  }

  /** Quadro da entrada de vídeo → ``motion:video`` para cada motion daquele dispositivo. */
  deliverVideo<B extends BitmapLike>(device: string, makeBitmap: () => B) {
    for (const f of this.frames) {
      if (f.device !== device) continue;
      const win = this.wins.get(f.sid);
      if (!win) continue;
      const frame = makeBitmap();
      win.postMessage({ type: "motion:video", payload: { frame, width: frame.width, height: frame.height, device } },
        "*", [frame as unknown as Transferable]);
    }
  }
}
