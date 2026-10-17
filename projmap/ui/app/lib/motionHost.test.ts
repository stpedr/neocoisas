import { describe, expect, it, vi } from "vitest";
import {
  MotionHostController,
  audioPayload,
  buildSrcdoc,
  createAudioState,
  packPacket,
  unpackPacket,
  type HostFrame,
  type HostSocket,
} from "./motionHost";

describe("protocolo binário", () => {
  it("pack/unpack ida e volta (cabeçalho JSON + corpo)", () => {
    const body = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
    const buf = packPacket({ sid: "m1", w: 1, h: 2 }, body);
    const { header, body: out } = unpackPacket(buf);
    expect(header).toEqual({ sid: "m1", w: 1, h: 2 });
    expect(Array.from(out)).toEqual(Array.from(body));
  });

  it("recusa pacote truncado", () => {
    expect(() => unpackPacket(new Uint8Array([200, 0, 0, 0, 1]).buffer)).toThrow();
  });
});

describe("buildSrcdoc", () => {
  it("injeta o shim logo no início do <head>, antes dos scripts do motion", () => {
    const html = '<!doctype html><html><head><script id="m">var x=1</script></head><body></body></html>';
    const out = buildSrcdoc(html, 30);
    const shim = out.indexOf("projmap:frame");
    expect(shim).toBeGreaterThan(-1);
    expect(shim).toBeLessThan(out.indexOf('id="m"'));
    expect(out).toContain("1000 / 30");
  });

  it("sem <head>, põe o shim no começo do documento", () => {
    const out = buildSrcdoc("<canvas></canvas>", 24);
    expect(out.startsWith("<script>")).toBe(true);
    expect(out.endsWith("<canvas></canvas>")).toBe(true);
  });
});

describe("audioPayload", () => {
  it("copia os níveis contínuos e dá impulso de beat/kick só no quadro da batida", () => {
    const st = createAudioState();
    const quiet = audioPayload(st, { bass: 0.2, mid: 0.1, high: 0.3, level: 0.4, beat: 0, beats: 0 }, 1000);
    expect(quiet).toMatchObject({ bass: 0.2, mid: 0.1, high: 0.3, level: 0.4, beat: 0, kick: 0 });
    const hit = audioPayload(st, { bass: 0.9, mid: 0.1, high: 0.3, level: 0.8, beat: 1, beats: 1 }, 1016);
    expect(hit.beat).toBe(1);
    expect(hit.kick).toBe(1);
    const after = audioPayload(st, { bass: 0.9, mid: 0.1, high: 0.3, level: 0.8, beat: 0.9, beats: 1 }, 1032);
    expect(after.beat).toBe(0);
  });

  it("não manda snare/hat (o motion cai no fallback 'beat' da spec)", () => {
    const p = audioPayload(createAudioState(), { bass: 0, mid: 0, high: 0, level: 0, beat: 0, beats: 0 }, 0);
    expect("snare" in p).toBe(false);
    expect("hat" in p).toBe(false);
  });

  it("estima o BPM e a fase depois de algumas batidas regulares; downbeat a cada 4", () => {
    const st = createAudioState();
    let downbeats = 0;
    for (let i = 1; i <= 8; i++) {
      const p = audioPayload(st, { bass: 1, mid: 0, high: 0, level: 1, beat: 1, beats: i }, i * 500);
      downbeats += p.downbeat;
    }
    const p = audioPayload(st, { bass: 0, mid: 0, high: 0, level: 0, beat: 0, beats: 8 }, 8 * 500 + 250);
    expect(p.bpm).toBeCloseTo(120, 0);
    expect(p.beatPhase).toBeCloseTo(0.5, 1);
    expect(downbeats).toBe(2);
  });

  it("energy é a média lenta do level", () => {
    const st = createAudioState();
    let p = audioPayload(st, { bass: 0, mid: 0, high: 0, level: 1, beat: 0, beats: 0 }, 0);
    for (let t = 16; t < 1000; t += 16) p = audioPayload(st, { bass: 0, mid: 0, high: 0, level: 1, beat: 0, beats: 0 }, t);
    expect(p.energy).toBeGreaterThan(0.1);
    expect(p.energy).toBeLessThan(0.6);
  });
});

// ------------------------------------------------------------------ controlador
class FakeSocket implements HostSocket {
  sent: (string | ArrayBuffer)[] = [];
  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }
}

function fakeWin() {
  return { postMessage: vi.fn() };
}

describe("MotionHostController", () => {
  const SESSION = { sid: "m1", media: "abc", w: 4, h: 2, params: { seed: 3 }, mode: "clean", device: "auto" };

  it("sincroniza as sessões e busca o HTML de cada mídia uma vez", async () => {
    const fetchHtml = vi.fn().mockResolvedValue("<html><head></head></html>");
    const onChange = vi.fn();
    const c = new MotionHostController({ socket: new FakeSocket(), fetchHtml, onChange });
    await c.handleText(JSON.stringify({ type: "sessions", sessions: [SESSION, { ...SESSION, sid: "m2" }] }));
    expect(fetchHtml).toHaveBeenCalledTimes(1);
    expect(fetchHtml).toHaveBeenCalledWith("/media/abc");
    expect(c.frames.map((f: HostFrame) => f.sid)).toEqual(["m1", "m2"]);
    expect(c.frames[0].srcdoc).toContain("projmap:frame");
    expect(onChange).toHaveBeenCalled();
  });

  it("no load do iframe manda motion:init embutido com params/mode e áudio externo", async () => {
    const c = new MotionHostController({ socket: new FakeSocket(), fetchHtml: async () => "<head></head>", onChange: () => {} });
    await c.handleText(JSON.stringify({ type: "sessions", sessions: [SESSION] }));
    const win = fakeWin();
    c.attach("m1", win);
    c.loaded("m1");
    expect(win.postMessage).toHaveBeenCalledWith(
      { type: "motion:init", payload: { embed: true, params: { seed: 3 }, mode: "clean", audioSource: "external" } },
      "*",
    );
  });

  it("áudio do mestre vira motion:audio para todos os motions", async () => {
    const c = new MotionHostController({ socket: new FakeSocket(), fetchHtml: async () => "", onChange: () => {} });
    await c.handleText(JSON.stringify({ type: "sessions", sessions: [SESSION] }));
    const win = fakeWin();
    c.attach("m1", win);
    await c.handleText(JSON.stringify({ type: "audio", bass: 0.5, mid: 0, high: 0, level: 0.5, beat: 0, beats: 0 }));
    const msg = win.postMessage.mock.calls.at(-1)![0];
    expect(msg.type).toBe("motion:audio");
    expect(msg.payload.bass).toBe(0.5);
  });

  it("quadro do motion vai ao mestre como JPEG com cabeçalho {sid,w,h,fmt}", () => {
    const socket = new FakeSocket();
    const c = new MotionHostController({ socket, fetchHtml: async () => "", onChange: () => {} });
    c.setSessions([SESSION]);
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
    expect(c.sendFrame("m1", jpeg, "jpeg")).toBe(true);
    const { header, body } = unpackPacket(socket.sent.at(-1) as ArrayBuffer);
    expect(header).toEqual({ sid: "m1", w: 4, h: 2, fmt: "jpeg" });
    expect(Array.from(body)).toEqual([0xff, 0xd8, 0xff, 0xd9]);
    c.sendFrame("m1", jpeg, "jpeg", [640, 360]); // canvas do motion com outro tamanho
    expect(unpackPacket(socket.sent.at(-1) as ArrayBuffer).header).toMatchObject({ w: 640, h: 360 });
    c.sendFrame("m1", new Uint8Array(4 * 2 * 4), "rgba", undefined, true);
    expect(unpackPacket(socket.sent.at(-1) as ArrayBuffer).header).toEqual(
      { sid: "m1", w: 4, h: 2, fmt: "rgba", flip_y: true },
    );
  });

  it("descarta o quadro se o WebSocket ainda está enviando o anterior (latência baixa)", () => {
    const socket = Object.assign(new FakeSocket(), { bufferedAmount: 5_000_000 });
    const c = new MotionHostController({ socket, fetchHtml: async () => "", onChange: () => {} });
    c.setSessions([SESSION]);
    expect(c.sendFrame("m1", new Uint8Array([1]), "jpeg")).toBe(false);
    expect(socket.sent).toHaveLength(0);
  });

  it("ack libera o shim do motion para o próximo quadro", () => {
    const c = new MotionHostController({ socket: new FakeSocket(), fetchHtml: async () => "", onChange: () => {} });
    c.setSessions([SESSION]);
    const win = fakeWin();
    c.attach("m1", win);
    c.ack("m1");
    expect(win.postMessage).toHaveBeenCalledWith({ type: "projmap:ack" }, "*");
  });

  it("quadro de vídeo vai só para os motions daquele dispositivo", async () => {
    const c = new MotionHostController({ socket: new FakeSocket(), fetchHtml: async () => "", onChange: () => {} });
    c.setSessions([SESSION, { ...SESSION, sid: "m2", device: null }]);
    const a = fakeWin();
    const b = fakeWin();
    c.attach("m1", a);
    c.attach("m2", b);
    const bitmap = { width: 8, height: 4, close: vi.fn() };
    c.deliverVideo("auto", () => bitmap);
    expect(a.postMessage).toHaveBeenCalledWith(
      { type: "motion:video", payload: { frame: bitmap, width: 8, height: 4, device: "auto" } },
      "*",
      [bitmap],
    );
    expect(b.postMessage).not.toHaveBeenCalled();
  });
});
