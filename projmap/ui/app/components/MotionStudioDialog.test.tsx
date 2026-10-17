import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyMotionPreset,
  computeAudioFrame,
  createBeatDetectorState,
  extractClaudeMotionResponse,
  parseAndValidateMotionHtml,
  runMotionSmokeTest,
  SAMPLE_MOTION_HTML,
  upsertMotionInLibrary,
  validateGeneratedMotionStrict,
  type MotionPreset,
} from "../lib/motionModule";
import MotionStudioDialog, { type ClaudeStreamGenerator } from "./MotionStudioDialog";

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
    expect(Object.keys(res.manifest.params)).toEqual(
      expect.arrayContaining(["speed", "rings", "mirror", "primaryColor", "palette", "cameraOffset"]),
    );
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

  it("A.5 MOTOR DE ÁUDIO PARA DJ: detecta kick em 128 BPM (< 1 BPM erro), hat não dispara kick, e AGC converge sinais de -20 dB e 0 dB", () => {
    const sampleRate = 44100;
    const fftSize = 2048; // binHz ≈ 21.53 Hz
    const silenceTime = new Uint8Array(fftSize).fill(128);

    // 1. Kick sintético em 128 BPM (período = 468.75 ms; passo de 15.625 ms = 30 frames por batida)
    const kickState = createBeatDetectorState();
    const dtMs = 15.625;
    for (let step = 0; step < 360; step++) {
      const nowMs = step * dtMs;
      const isKickFrame = step % 30 === 0;
      const freq = new Uint8Array(1024).fill(5);
      // Banda do kick: 40–120 Hz -> bins 1..6
      for (let b = 1; b <= 6; b++) {
        freq[b] = isKickFrame ? 245 : 8;
      }
      computeAudioFrame(freq, silenceTime, sampleRate, fftSize, kickState, nowMs);
    }
    expect(kickState.bpmLocked).toBe(true);
    expect(Math.abs(kickState.bpm - 128)).toBeLessThan(1);

    // 2. Hat (6–14 kHz, bins 278..651) dispara hat > 0 mas NUNCA dispara kick
    const hatState = createBeatDetectorState();
    let hatTriggers = 0;
    let kickTriggersDuringHat = 0;
    for (let step = 0; step < 120; step++) {
      const nowMs = step * 16;
      const isHatPulse = step % 8 === 0;
      const freq = new Uint8Array(1024).fill(0);
      if (isHatPulse) {
        for (let b = 280; b <= 640; b++) {
          freq[b] = 230;
        }
      }
      const { frame } = computeAudioFrame(freq, silenceTime, sampleRate, fftSize, hatState, nowMs);
      if (frame.hat > 0) hatTriggers += 1;
      if (frame.kick > 0) kickTriggersDuringHat += 1;
    }
    expect(hatTriggers).toBeGreaterThan(3);
    expect(kickTriggersDuringHat).toBe(0);

    // 3. Sinal de -20 dB (amplitude 0.1 -> bin=25) e de 0 dB (amplitude 1.0 -> bin=250) convergem após o AGC para o mesmo bass
    const state0dB = createBeatDetectorState();
    const stateMinus20dB = createBeatDetectorState();
    const freq0dB = new Uint8Array(1024).fill(0);
    const freqMinus20dB = new Uint8Array(1024).fill(0);
    for (let b = 1; b <= 7; b++) {
      freq0dB[b] = 250;
      freqMinus20dB[b] = 25;
    }
    let lastBass0dB = 0;
    let lastBassMinus20dB = 0;
    for (let i = 0; i < 600; i++) {
      const tMs = i * 50; // 30 segundos simulados
      lastBass0dB = computeAudioFrame(freq0dB, silenceTime, sampleRate, fftSize, state0dB, tMs).frame.bass;
      lastBassMinus20dB = computeAudioFrame(
        freqMinus20dB,
        silenceTime,
        sampleRate,
        fftSize,
        stateMinus20dB,
        tMs,
      ).frame.bass;
    }
    expect(lastBass0dB).toBeGreaterThan(0.5);
    expect(Math.abs(lastBass0dB - lastBassMinus20dB)).toBeLessThan(0.02);
  });

  it("B. PAINEL DE REAÇÃO DA CAMADA: barra segmentada reactTo, bloqueio de rx_*_src fora de custom, atalhos 1–5 e aplicar a todas as camadas", () => {
    const parsed1 = parseAndValidateMotionHtml(SAMPLE_MOTION_HTML);
    const secondHtml = SAMPLE_MOTION_HTML.replace('"id": "neon-pulse-grid"', '"id": "cyber-rings"').replace(
      '"name": "Neon Pulse Grid"',
      '"name": "Cyber Rings"',
    );
    const parsed2 = parseAndValidateMotionHtml(secondHtml);
    if (!parsed1.ok || !parsed2.ok) throw new Error("manifest parse failed");

    let lib = upsertMotionInLibrary([], parsed1.manifest, parsed1.html);
    lib = upsertMotionInLibrary(lib, parsed2.manifest, parsed2.html);
    localStorage.setItem("projmap.motions.library.v1", JSON.stringify(lib));

    render(<MotionStudioDialog open={true} onClose={() => {}} />);

    const execButtons = screen.getAllByRole("button", { name: /▶ Executar/i });
    fireEvent.click(execButtons[0]);
    fireEvent.click(execButtons[1]);

    // Em reactTo="mix" (default), os dropdowns rx_*_src ficam desabilitados
    const deformSrcSelects = screen.getAllByLabelText("Deformação · Fonte") as HTMLSelectElement[];
    expect(deformSrcSelects[0]).toBeDisabled();
    expect(deformSrcSelects[0].value).toBe("bass");

    // Clicar em "[5] Personalizado" no 2º slot (selecionado) habilita o dropdown rx_*_src
    const customButtons = screen.getAllByRole("button", { name: /\[5\] Personalizado/i });
    fireEvent.click(customButtons[1]);
    expect(deformSrcSelects[1]).not.toBeDisabled();

    // Alterar rx_deform_src para "high" e voltar para "bass" via tecla "2" preserva o valor salvo mas desabilita o select
    fireEvent.change(deformSrcSelects[1], { target: { value: "high" } });
    expect(deformSrcSelects[1].value).toBe("high");

    fireEvent.keyDown(window, { key: "2" }); // Atalho [2] Graves (bass)
    expect(deformSrcSelects[1]).toBeDisabled();
    expect(deformSrcSelects[1].value).toBe("high");

    // Botão "Aplicar reactTo a todas as camadas" propaga "bass" para todas as camadas ativas
    const applyAllButtons = screen.getAllByRole("button", { name: /Aplicar reactTo a todas as camadas/i });
    fireEvent.click(applyAllButtons[1]);
    const bassButtons = screen.getAllByRole("button", { name: /\[2\] Graves/i });
    expect(bassButtons[0].className).toContain("on");
    expect(bassButtons[1].className).toContain("on");
  });

  it("C.6 GERADOR CLAUDE (a, b, c, d): (a) válido de 1ª, (b) sem <layer_preset>, (c) reparado na 2ª tentativa, (d) falha após 3 reparos", async () => {
    // Valida que SAMPLE_MOTION_HTML passa na validação estrita do gerador (C.4 Etapa 1)
    expect(validateGeneratedMotionStrict(SAMPLE_MOTION_HTML).ok).toBe(true);

    // (b) Verifica que extractClaudeMotionResponse detecta ausência de <layer_preset>
    const missingPresetRes = extractClaudeMotionResponse(
      `<motion_html>${SAMPLE_MOTION_HTML}</motion_html><notes>Sem preset</notes>`,
    );
    expect(missingPresetRes.ok).toBe(false);
    expect(missingPresetRes.errors.some((e) => e.includes("<layer_preset>"))).toBe(true);

    const mockSmokeOk = vi.fn().mockResolvedValue({ ok: true, errors: [], beatEventsReceived: 4 });

    // (a) Motion válido de primeira -> importa na biblioteca e cria preset "Camada"
    const genValidFirst: ClaudeStreamGenerator = vi.fn().mockResolvedValue({
      ok: true,
      html: SAMPLE_MOTION_HTML,
      layer_preset: { mode: "cyber", params: { framing: "element", background: "transparent", reactTo: "beat" } },
      notes: "Alvos: deform (kick) e pulse (bass).",
      errors: [],
      usage: {
        input_tokens: 1200,
        output_tokens: 1800,
        cache_creation_input_tokens: 1000,
        cache_read_input_tokens: 0,
        estimated_cost_usd: 0.16,
      },
    });

    const { unmount } = render(
      <MotionStudioDialog
        open={true}
        onClose={() => {}}
        claudeGenerator={genValidFirst}
        smokeTestRunner={mockSmokeOk}
      />,
    );

    fireEvent.click(screen.getByTestId("tab-generate-claude"));
    // Sugestão clicável preenche o campo
    fireEvent.click(screen.getByRole("button", { name: /anéis de luz que explodem no kick/i }));
    await act(async () => {
      fireEvent.click(screen.getByTestId("btn-run-claude"));
    });

    expect(genValidFirst).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("motion-library-list")).toHaveTextContent("neon-pulse-grid@1.0.0");
    // Preset "Camada" criado automaticamente a partir de <layer_preset>
    expect(screen.getByRole("button", { name: /Camada \(v1\.0\.0\)/i })).toBeInTheDocument();
    unmount();

    // (c) Erro no manifesto / sem <layer_preset> na 1ª resposta -> corrigido automaticamente na 2ª chamada (kind: "repair")
    localStorage.clear();
    const brokenHtml = SAMPLE_MOTION_HTML.replace('"reactTo"', '"missingReactTo"');
    const genFixedOnSecond: ClaudeStreamGenerator = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        html: brokenHtml,
        layer_preset: {},
        notes: "",
        errors: ["Marcação <layer_preset>...</layer_preset> ausente ou vazia."],
        usage: {
          input_tokens: 1000,
          output_tokens: 1500,
          cache_creation_input_tokens: 0,
          cache_read_input_tokens: 900,
          estimated_cost_usd: 0.12,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        html: SAMPLE_MOTION_HTML,
        layer_preset: { mode: "cyber", params: { framing: "element", background: "transparent" } },
        notes: "Corrigido na tentativa de reparo.",
        errors: [],
        usage: {
          input_tokens: 1400,
          output_tokens: 1600,
          cache_creation_input_tokens: 0,
          cache_read_input_tokens: 900,
          estimated_cost_usd: 0.13,
        },
      });

    const { unmount: unmount2 } = render(
      <MotionStudioDialog
        open={true}
        onClose={() => {}}
        claudeGenerator={genFixedOnSecond}
        smokeTestRunner={mockSmokeOk}
      />,
    );

    fireEvent.click(screen.getByTestId("tab-generate-claude"));
    fireEvent.change(screen.getByLabelText("Descrição do motion"), {
      target: { value: "esfera líquida cromada" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("btn-run-claude"));
    });

    expect(genFixedOnSecond).toHaveBeenCalledTimes(2);
    expect(vi.mocked(genFixedOnSecond).mock.calls[0][0].kind).toBe("new");
    expect(vi.mocked(genFixedOnSecond).mock.calls[1][0].kind).toBe("repair");
    expect(vi.mocked(genFixedOnSecond).mock.calls[1][0].errors?.join(" ")).toContain("reactTo");
    expect(screen.getByTestId("motion-library-list")).toHaveTextContent("neon-pulse-grid@1.0.0");
    unmount2();

    // (d) Motion que falha nas 3 tentativas de reparo -> para, exibe os erros e oferece "Tentar de novo" e "Importar mesmo assim"
    localStorage.clear();
    const genAlwaysFails: ClaudeStreamGenerator = vi.fn().mockResolvedValue({
      ok: true,
      html: brokenHtml,
      layer_preset: { mode: "cyber", params: { framing: "element", background: "transparent" } },
      notes: "Rascunho com falha",
      errors: [],
      usage: {
        input_tokens: 800,
        output_tokens: 900,
        cache_creation_input_tokens: 0,
        cache_read_input_tokens: 700,
        estimated_cost_usd: 0.08,
      },
    });

    render(
      <MotionStudioDialog
        open={true}
        onClose={() => {}}
        claudeGenerator={genAlwaysFails}
        smokeTestRunner={mockSmokeOk}
      />,
    );

    fireEvent.click(screen.getByTestId("tab-generate-claude"));
    fireEvent.change(screen.getByLabelText("Descrição do motion"), {
      target: { value: "túnel quebrado" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("btn-run-claude"));
    });

    // 1 chamada inicial ("new") + 3 tentativas de reparo ("repair") = 4 chamadas
    expect(genAlwaysFails).toHaveBeenCalledTimes(4);
    const failureBox = screen.getByTestId("claude-repair-failure");
    expect(failureBox).toHaveTextContent("reactTo");
    expect(within(failureBox).getByRole("button", { name: /Tentar de novo/i })).toBeInTheDocument();
    expect(within(failureBox).getByRole("button", { name: /Importar mesmo assim/i })).toBeInTheDocument();
  });

  it("C.6 TESTE DE FUMAÇA (runMotionSmokeTest): falha quando o motion emite motion:error ao inicializar", async () => {
    vi.useRealTimers();
    const origAppend = document.body.appendChild.bind(document.body);
    vi.spyOn(document.body, "appendChild").mockImplementation((node: Node) => {
      const res = origAppend(node);
      if (node instanceof HTMLIFrameElement) {
        const fakeWin = {
          postMessage: (msg: { type?: string }) => {
            if (msg?.type === "motion:init") {
              window.dispatchEvent(
                new MessageEvent("message", {
                  data: { type: "motion:ready", payload: { phase: "active" } },
                  source: fakeWin as unknown as Window,
                }),
              );
              window.dispatchEvent(
                new MessageEvent("message", {
                  data: { type: "motion:error", payload: { message: "ReferenceError: shaderUniform is not defined" } },
                  source: fakeWin as unknown as Window,
                }),
              );
            }
          },
        };
        Object.defineProperty(node, "contentWindow", { value: fakeWin, configurable: true });
        setTimeout(() => node.onload?.(new Event("load")), 5);
      }
      return res;
    });

    const result = await runMotionSmokeTest(
      SAMPLE_MOTION_HTML,
      { mode: "cyber", params: { framing: "element", background: "transparent" } },
      { readyTimeoutMs: 200, audioDurationMs: 60, stepMs: 20 },
    );

    expect(result.ok).toBe(false);
    expect(result.errors.join(" ")).toContain("ReferenceError: shaderUniform is not defined");
  });
});
