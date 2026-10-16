import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InteractPanel from "./InteractPanel";
import { api } from "../lib/api";
import type { InteractState } from "../lib/types";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      effects: vi.fn().mockResolvedValue({ imported: true, hint: "", effects: {} }),
      interactPresets: vi.fn().mockResolvedValue({
        "fantasmas-timidos": { title: "Fantasmas tímidos", description: "Param quando olhados" },
      }),
      interactPreset: vi.fn(),
      interactAuto: vi.fn(),
      interactPlayer: vi.fn(),
      interactDebug: vi.fn(),
      interactPause: vi.fn(),
      interactReset: vi.fn(),
    },
  };
});

function estado(overrides: Partial<InteractState> = {}): InteractState {
  return {
    spec: { title: "Fantasmas tímidos", description: "", groups: [] },
    sensor: "sim",
    scripted: false,
    paused: false,
    debug: false,
    tick: 0,
    entities: [
      { id: 1, group: "ghost", x: 0.2, y: 0.5, state: "move" },
      { id: 2, group: "ghost", x: 0.6, y: 0.5, state: "shy" },
    ],
    players: [{ id: 1, x: 0.5, distance: 2, yaw_deg: 10, tracked: true, watching: true, gaze: [0, 0, 0] }],
    events: [],
    effect: null,
    ...overrides,
  } as unknown as InteractState;
}

function setSt() {}

describe("InteractPanel", () => {
  beforeEach(() => {
    vi.mocked(api.interactPreset).mockReset().mockResolvedValue(estado());
    vi.mocked(api.interactAuto).mockReset().mockResolvedValue(estado());
    vi.mocked(api.interactPlayer).mockReset().mockResolvedValue(estado());
    vi.mocked(api.interactDebug).mockReset().mockResolvedValue(estado());
    vi.mocked(api.interactPause).mockReset().mockResolvedValue(estado());
    vi.mocked(api.interactReset).mockReset().mockResolvedValue(estado());
  });

  it("mostra o sensor atual e o botão de criar cena com IA", async () => {
    const onOpenAi = vi.fn();
    render(<InteractPanel st={estado()} setSt={setSt} caught={false} onError={() => {}} onOpenAi={onOpenAi} />);

    expect(screen.getByText(/pessoa simulada/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Criar cena com IA/ }));
    expect(onOpenAi).toHaveBeenCalled();
  });

  it("lista os presets e clicar aplica um deles", async () => {
    render(<InteractPanel st={estado()} setSt={setSt} caught={false} onError={() => {}} onOpenAi={() => {}} />);

    const preset = await screen.findByRole("button", { name: "Fantasmas tímidos" });
    await userEvent.click(preset);
    expect(api.interactPreset).toHaveBeenCalledWith("fantasmas-timidos");
  });

  it("mostra o resumo do estado: elementos, contagem e 'Pegou!' quando caught", () => {
    render(<InteractPanel st={estado()} setSt={setSt} caught onError={() => {}} onOpenAi={() => {}} />);

    expect(screen.getByText(/2 elementos/)).toBeInTheDocument();
    expect(screen.getByText(/1 em movimento/)).toBeInTheDocument();
    expect(screen.getByText(/Pegou!/)).toBeInTheDocument();
  });

  it("sensor sim: os botões de pessoa simulada chamam a API certa", async () => {
    render(<InteractPanel st={estado()} setSt={setSt} caught={false} onError={() => {}} onOpenAi={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Automático" }));
    expect(api.interactAuto).toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Olhar a parede" }));
    expect(api.interactPlayer).toHaveBeenCalledWith({ yaw_deg: 0, tracked: true });

    await userEvent.click(screen.getByRole("button", { name: "Virar de costas" }));
    expect(api.interactPlayer).toHaveBeenCalledWith({ yaw_deg: 180, tracked: true });
  });

  it("mover o slider de posição pelo teclado chama interactPlayer com x atualizado", async () => {
    render(<InteractPanel st={estado()} setSt={setSt} caught={false} onError={() => {}} onOpenAi={() => {}} />);

    const posicao = screen.getByRole("slider", { name: /Posição na parede/ });
    posicao.focus();
    await userEvent.keyboard("{ArrowRight}");

    expect(api.interactPlayer).toHaveBeenCalledWith({ x: expect.any(Number) });
  });

  it("'Mostrar olhar' chama interactDebug, e Pausar/Reiniciar chamam suas APIs", async () => {
    render(<InteractPanel st={estado()} setSt={setSt} caught={false} onError={() => {}} onOpenAi={() => {}} />);

    await userEvent.click(screen.getByRole("checkbox", { name: "Mostrar olhar" }));
    expect(api.interactDebug).toHaveBeenCalledWith(true);

    await userEvent.click(screen.getByRole("button", { name: "Pausar" }));
    expect(api.interactPause).toHaveBeenCalledWith(true);

    await userEvent.click(screen.getByRole("button", { name: "Reiniciar" }));
    expect(api.interactReset).toHaveBeenCalled();
  });

  it("sensor phone: mostra o status de conexão do celular em vez do bloco de simulação", () => {
    render(
      <InteractPanel
        st={estado({ sensor: "phone", phone: { connected: 1, fps: 24 } })}
        setSt={setSt}
        caught={false}
        onError={() => {}}
        onOpenAi={() => {}}
      />,
    );
    expect(screen.getByText(/conectado \(24 fps\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Pessoa simulada/)).not.toBeInTheDocument();
  });
});
