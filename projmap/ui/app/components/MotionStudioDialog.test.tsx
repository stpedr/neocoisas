import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyMotionPreset,
  computeAudioFrame,
  createBeatDetectorState,
  parseAndValidateMotionHtml,
  SAMPLE_MOTION_HTML,
  upsertMotionInLibrary,
  type MotionPreset,
} from "../lib/motionModule";
import MotionStudioDialog from "./MotionStudioDialog";

function makeHtmlWithManifest(manifest: Record<string, unknown>): string {
  return `<!DOCTYPE html><html><head><script type="application/json" id="motion-manifest">${JSON.stringify(
    manifest,
  )}</script></head><body></body></html>`;
}

describe("Motion Module v1 — Validação, Biblioteca, Execução, Presets, Áudio e Ciclo de Vida", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
    if (!URL.createObjectURL) {
      Object.defineProperty(URL, "createObjectURL", {
        writable: true,
        value: vi.fn(() => "blob:http://localhost/mock-motion-blob"),
      });
    } else {
      vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:http://localhost/mock-${Math.random()}`);
    }
    if (!URL.revokeObjectURL) {
      Object.defineProperty(URL, "revokeObjectURL", {
        writable: true,
        value: vi.fn(),
      });
    } else {
      vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    }
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("1. IMPORTAÇÃO: valida manifesto válido com todos os 6 tipos de params (float, int, bool, color, select, vec3)", () => {
    const res = parseAndValidateMotionHtml(SAMPLE_MOTION_HTML);
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.manifest.spec).toBe("motion-module/1");
    expect(res.manifest.id).toBe("neon-pulse-grid");
    expect(res.manifest.name).toBe("Neon Pulse Grid");
    expect(res.manifest.version).toBe("1.0.0");
    expect(Object.keys(res.manifest.params)).toEqual([
      "speed",
      "rings",
      "mirror",
      "primaryColor",
      "palette",
      "cameraOffset",
    ]);
  });

  it("1. IMPORTAÇÃO: aponta exatamente qual campo está errado quando a validação falha", () => {
    const badHtml = makeHtmlWithManifest({
      spec: "motion-module/99",
      id: "",
      name: "Teste Inválido",
      // version ausente
      params: {
        badType: { type: "matrix4", default: 1 },
        outOfRangeFloat: { type: "float", min: 0, max: 5, default: 10 },
        nonInt: { type: "int", min: 0, max: 10, default: 3.5 },
        badBool: { type: "bool", default: "yes" },
        badColor: { type: "color", default: "not-a-color" },
        badSelect: { type: "select", options: ["a", "b"], default: "c" },
        badVec3: { type: "vec3", min: -1, max: 1, default: [0, 5, 0] },
      },
    });

    const res = parseAndValidateMotionHtml(badHtml);
    expect(res.ok).toBe(false);
    if (res.ok) return;
    const fields = res.errors.map((e) => e.field);
    expect(fields).toContain("spec");
    expect(fields).toContain("id");
    expect(fields).toContain("version");
    expect(fields).toContain("params.badType.type");
    expect(fields).toContain("params.outOfRangeFloat.default");
    expect(fields).toContain("params.nonInt.default");
    expect(fields).toContain("params.badBool.default");
    expect(fields).toContain("params.badColor.default");
    expect(fields).toContain("params.badSelect.default");
    expect(fields).toContain("params.badVec3.default");
  });

  it("2. BIBLIOTECA: identifica por id + version e pergunta se substitui ou mantém as duas versões", async () => {
    render(<MotionStudioDialog open={true} onClose={() => {}} />);

    // Carrega v1.0.0
    fireEvent.click(screen.getByRole("button", { name: /\+ Carregar Exemplo v1/i }));
    expect(screen.getByTestId("motion-library-list")).toHaveTextContent("neon-pulse-grid@1.0.0");

    // Importa o mesmo id na versão 2.0.0 via dropzone
    const v2Html = SAMPLE_MOTION_HTML.replace('"version": "1.0.0"', '"version": "2.0.0"');
    const dropzone = screen.getByTestId("motion-dropzone");
    const file = new File([v2Html], "neon-v2.html", { type: "text/html" });
    Object.defineProperty(file, "text", { value: () => Promise.resolve(v2Html) });

    await act(async () => {
      fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
    });

    const prompt = screen.getByTestId("motion-conflict-prompt");
    expect(prompt).toHaveTextContent("neon-pulse-grid");
    expect(prompt).toHaveTextContent("2.0.0");

    // Escolhe "Manter as duas versões"
    fireEvent.click(within(prompt).getByRole("button", { name: /Manter as duas versões/i }));
    const libList = screen.getByTestId("motion-library-list");
    expect(libList).toHaveTextContent("neon-pulse-grid@1.0.0");
    expect(libList).toHaveTextContent("neon-pulse-grid@2.0.0");
  });

  it("3 & 8. EXECUÇÃO + CICLO DE VIDA: sandbox='allow-scripts' sem allow-same-origin, motion:init -> timeout 5s ou motion:ready, filtro de event.source e motion:destroy + revokeObjectURL", () => {
    render(<MotionStudioDialog open={true} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /\+ Carregar Exemplo v1/i }));

    const iframe = screen.getByTitle(/Motion Neon Pulse Grid/i) as HTMLIFrameElement;
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("sandbox")).not.toContain("allow-same-origin");

    const postMessageSpy = vi.fn();
    const fakeContentWindow = { postMessage: postMessageSpy } as unknown as Window;
    Object.defineProperty(iframe, "contentWindow", { value: fakeContentWindow, configurable: true });

    // Dispara load do iframe -> deve enviar motion:init { embed: true, audioSource: "external" }
    fireEvent.load(iframe);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: "motion:init", payload: { embed: true, audioSource: "external" } },
      "*",
    );

    // Mensagem de outro source deve ser ignorada
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "motion:ready", payload: { phase: "hacked" } },
          source: window, // diferente de fakeContentWindow
        }),
      );
    });
    expect(screen.getByText(/Iniciando…/i)).toBeInTheDocument();

    // Avança 5s sem resposta -> marca como erro
    act(() => {
      vi.advanceTimersByTime(5001);
    });
    expect(screen.getByText(/Erro \(Timeout 5s\)/i)).toBeInTheDocument();

    // Agora envia motion:ready do contentWindow correto -> fica pronto e atualiza fase
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "motion:ready", payload: { phase: "intro" } },
          source: fakeContentWindow,
        }),
      );
    });
    expect(screen.getByText(/Pronto \(motion:ready\)/i)).toBeInTheDocument();

    // 4. PAINEL AUTOMÁTICO: alterar parâmetro envia motion:setParams na hora
    const speedInput = screen.getByLabelText("Velocidade valor");
    fireEvent.change(speedInput, { target: { value: "2.5" } });
    expect(postMessageSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "motion:setParams",
        payload: expect.objectContaining({ speed: 2.5 }),
      }),
      "*",
    );

    // 8. CICLO DE VIDA: remover o motion envia motion:destroy e revoga o blob URL
    fireEvent.click(screen.getByRole("button", { name: /Remover Motion/i }));
    expect(postMessageSpy).toHaveBeenCalledWith({ type: "motion:destroy", payload: {} }, "*");
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  it("5. PRESETS: ignora params removidos, limita valores ao range atual e avisa se a versão for diferente", () => {
    const parsed = parseAndValidateMotionHtml(SAMPLE_MOTION_HTML);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    const preset: MotionPreset = {
      id: "p1",
      name: "Preset Antigo",
      motionId: "neon-pulse-grid",
      motionVersion: "0.9.0",
      mode: "cyber",
      params: {
        speed: 999, // acima de max=5.0 -> deve virar 5.0
        rings: -5, // abaixo de min=1 -> deve virar 1
        cameraOffset: [-10, 0.5, 10], // fora de [-2, 2] -> [-2, 0.5, 2]
        obsoleteParam: 42, // não existe mais -> deve ser ignorado
      },
      createdAt: "2026-01-01T00:00:00Z",
    };

    const applied = applyMotionPreset(preset, parsed.manifest);
    expect(applied.versionMismatch).toBe(true);
    expect(applied.warning).toContain("v0.9.0");
    expect(applied.warning).toContain("v1.0.0");
    expect(applied.ignoredParams).toEqual(["obsoleteParam"]);
    expect(applied.params.obsoleteParam).toBeUndefined();
    expect(applied.params.speed).toBe(5);
    expect(applied.params.rings).toBe(1);
    expect(applied.params.cameraOffset).toEqual([-2, 0.5, 2]);
  });

  it("6 & 7. ÁUDIO CENTRAL + REGRAS: calcula bandas 0-1, sincroniza vários motions e executa regras de phase/beat", () => {
    // Verifica cálculo das bandas FFT (bass 25-140Hz, mid 250-2200Hz, high 4-12kHz) em 0..1
    const freq = new Uint8Array(1024).fill(200);
    const time = new Uint8Array(2048).fill(220);
    const beatState = createBeatDetectorState();
    const { frame, triggered } = computeAudioFrame(freq, time, 44100, 2048, beatState, 1000);
    expect(frame.bass).toBeGreaterThan(0.5);
    expect(frame.bass).toBeLessThanOrEqual(1);
    expect(frame.mid).toBeGreaterThan(0.5);
    expect(frame.high).toBeGreaterThan(0.5);
    expect(frame.level).toBeGreaterThan(0.5);
    expect(frame.beat).toBe(1);
    expect(triggered).toBe(true);

    // Verifica sincronia de áudio e regras de fase/beat no componente
    const parsed1 = parseAndValidateMotionHtml(SAMPLE_MOTION_HTML);
    const secondHtml = SAMPLE_MOTION_HTML.replace('"id": "neon-pulse-grid"', '"id": "laser-tunnel"').replace(
      '"name": "Neon Pulse Grid"',
      '"name": "Laser Tunnel"',
    );
    const parsed2 = parseAndValidateMotionHtml(secondHtml);
    if (!parsed1.ok || !parsed2.ok) throw new Error("manifest parse failed");

    let lib = upsertMotionInLibrary([], parsed1.manifest, parsed1.html);
    lib = upsertMotionInLibrary(lib, parsed2.manifest, parsed2.html);
    localStorage.setItem("projmap.motions.library.v1", JSON.stringify(lib));
    localStorage.setItem(
      "projmap.motions.rules.v1",
      JSON.stringify([
        {
          id: "r-beat",
          enabled: true,
          kind: "beat_trigger",
          everyNBeats: 2,
          triggerId: "reset",
        },
        {
          id: "r-phase",
          enabled: true,
          kind: "phase_switch",
          whenPhase: "clean",
          targetMotionKey: "laser-tunnel@1.0.0",
        },
      ]),
    );

    render(<MotionStudioDialog open={true} onClose={() => {}} />);

    // Executa os dois motions simultaneamente
    const execButtons = screen.getAllByRole("button", { name: /▶ Executar/i });
    fireEvent.click(execButtons[0]);
    fireEvent.click(execButtons[1]);

    const iframes = document.querySelectorAll("iframe");
    expect(iframes.length).toBe(2);
    const spy1 = vi.fn();
    const spy2 = vi.fn();
    const win1 = { postMessage: spy1 } as unknown as Window;
    const win2 = { postMessage: spy2 } as unknown as Window;
    Object.defineProperty(iframes[0], "contentWindow", { value: win1, configurable: true });
    Object.defineProperty(iframes[1], "contentWindow", { value: win2, configurable: true });

    // Envia 2 pulsos de beat: ambos recebem motion:audio e no 2º beat disparam trigger "reset"
    const pulseBtn = screen.getByRole("button", { name: /Pulso de Beat/i });
    fireEvent.click(pulseBtn);
    expect(spy1).toHaveBeenCalledWith(expect.objectContaining({ type: "motion:audio" }), "*");
    expect(spy2).toHaveBeenCalledWith(expect.objectContaining({ type: "motion:audio" }), "*");

    fireEvent.click(pulseBtn);
    expect(spy1).toHaveBeenCalledWith({ type: "motion:trigger", payload: { id: "reset", name: "reset" } }, "*");
    expect(spy2).toHaveBeenCalledWith({ type: "motion:trigger", payload: { id: "reset", name: "reset" } }, "*");

    // Quando o 1º motion envia motion:state { phase: "clean" }, a regra troca o slot 1 para laser-tunnel@1.0.0
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "motion:state", payload: { phase: "clean" } },
          source: win1,
        }),
      );
    });
    expect(screen.getAllByText("Laser Tunnel").length).toBeGreaterThanOrEqual(2);
  });
});
