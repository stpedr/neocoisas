import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EffectsSection from "./EffectsSection";
import { api } from "../lib/api";
import type { EffectParams, EffectsCatalog, InteractState } from "../lib/types";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: { ...actual.api, effects: vi.fn(), setEffect: vi.fn(), effectParams: vi.fn() },
  };
});

const CATALOGO: EffectsCatalog = {
  imported: true,
  hint: "",
  effects: {
    "vf-luz": { title: "Luz reativa", description: "Pontos neon no contorno", available: true },
    "vf-lego": { title: "LEGO", description: "Mosaico de peças", available: true },
  },
};

const PARAMS_PADRAO: EffectParams = {
  orbes_maos: false,
  cor_segue_musica: true,
  matiz_fixo: 0.5,
  sensibilidade_som: 1,
  quantidade_ecos: 3,
  distancia_ecos: 4,
  tamanho_peca: 18,
  lego_cair: true,
  animal: 0,
  fundo_colorido: false,
  intervalo_aviao: 8,
  brilho: 1,
};

function estado(overrides: Partial<InteractState> = {}): InteractState {
  return {
    spec: { title: "" },
    entities: [],
    players: [],
    sensor: "sim",
    scripted: false,
    paused: false,
    debug: false,
    effect: null,
    effect_params: null,
    effect_status: null,
    ...overrides,
  } as unknown as InteractState;
}

describe("EffectsSection", () => {
  beforeEach(() => {
    vi.mocked(api.effects).mockReset();
    vi.mocked(api.setEffect).mockReset();
    vi.mocked(api.effectParams).mockReset();
  });

  it("sem catálogo carregado ainda, não renderiza nada", () => {
    vi.mocked(api.effects).mockReturnValue(new Promise(() => {})); // nunca resolve
    const { container } = render(<EffectsSection st={null} onState={() => {}} onError={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("catálogo não importado mostra a dica do comando", async () => {
    vi.mocked(api.effects).mockResolvedValue({ ...CATALOGO, imported: false });
    render(<EffectsSection st={null} onState={() => {}} onError={() => {}} />);
    expect(await screen.findByText(/projmap.effects.importar/)).toBeInTheDocument();
  });

  it("lista um botão por efeito do catálogo", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    render(<EffectsSection st={null} onState={() => {}} onError={() => {}} />);
    expect(await screen.findByRole("button", { name: "Luz reativa" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "LEGO" })).toBeInTheDocument();
  });

  it("clicar num efeito chama api.setEffect e repassa o novo estado", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    vi.mocked(api.setEffect).mockResolvedValue(estado({ effect: "vf-luz" }));
    const onState = vi.fn();
    render(<EffectsSection st={null} onState={onState} onError={() => {}} />);

    await userEvent.click(await screen.findByRole("button", { name: "Luz reativa" }));

    expect(api.setEffect).toHaveBeenCalledWith("vf-luz");
    await waitFor(() => expect(onState).toHaveBeenCalledWith(estado({ effect: "vf-luz" })));
  });

  it("com efeito ativo, mostra 'Voltar à cena' e os sliders compartilhados (Brilho, Sensibilidade)", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    const st = estado({ effect: "vf-luz", effect_params: PARAMS_PADRAO });
    render(<EffectsSection st={st} onState={() => {}} onError={() => {}} />);

    await screen.findByRole("button", { name: "Voltar à cena" });
    expect(screen.getByRole("slider", { name: /Brilho/ })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /Sensibilidade ao som/ })).toBeInTheDocument();
  });

  it("mover o slider de Brilho chama api.effectParams com o novo valor", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    vi.mocked(api.effectParams).mockResolvedValue(estado({ effect: "vf-luz", effect_params: PARAMS_PADRAO }));
    const st = estado({ effect: "vf-luz", effect_params: PARAMS_PADRAO });
    render(<EffectsSection st={st} onState={() => {}} onError={() => {}} />);

    const brilho = await screen.findByRole("slider", { name: /Brilho/ });
    brilho.focus();
    await userEvent.keyboard("{ArrowRight}");

    expect(api.effectParams).toHaveBeenCalledTimes(1);
    expect(api.effectParams.mock.calls[0][0]).toHaveProperty("brilho");
  });

  it("efeito vf-luz mostra os toggles próprios (Orbes nas mãos, Cor segue a música)", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    const st = estado({ effect: "vf-luz", effect_params: PARAMS_PADRAO });
    render(<EffectsSection st={st} onState={() => {}} onError={() => {}} />);

    expect(await screen.findByRole("checkbox", { name: "Orbes nas mãos" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Cor segue a música" })).toBeInTheDocument();
  });

  it("efeito vf-lego não mostra os controles do vf-luz", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    const st = estado({ effect: "vf-lego", effect_params: PARAMS_PADRAO });
    render(<EffectsSection st={st} onState={() => {}} onError={() => {}} />);

    await screen.findByRole("slider", { name: /Tamanho da peça/ });
    expect(screen.queryByRole("checkbox", { name: "Orbes nas mãos" })).not.toBeInTheDocument();
  });

  it("'Voltar à cena' chama setEffect('off')", async () => {
    vi.mocked(api.effects).mockResolvedValue(CATALOGO);
    vi.mocked(api.setEffect).mockResolvedValue(estado());
    const st = estado({ effect: "vf-luz", effect_params: PARAMS_PADRAO });
    render(<EffectsSection st={st} onState={() => {}} onError={() => {}} />);

    await userEvent.click(await screen.findByRole("button", { name: "Voltar à cena" }));
    expect(api.setEffect).toHaveBeenCalledWith("off");
  });
});
