import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DetectPanel from "./DetectPanel";
import { api } from "../lib/api";
import type { DetectCandidate } from "../lib/types";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, api: { ...actual.api, detect: vi.fn() } };
});

const QUAD = [[0, 0], [1, 0], [1, 1], [0, 1]] as DetectCandidate["quad"];
const CANDIDATOS: DetectCandidate[] = [
  { quad: QUAD, polygon: QUAD, score: 0.92, area: 0.3, label: "Parede 1", color: [200, 60, 60] },
  { quad: QUAD, polygon: QUAD, score: 0.6, area: 0.1, label: "Porta", color: [60, 200, 60] },
];

function setup(overrides: Partial<React.ComponentProps<typeof DetectPanel>> = {}) {
  const props = {
    nodeId: "n1",
    hasPhoto: true,
    candidates: [] as DetectCandidate[],
    selected: new Set<number>(),
    onResult: vi.fn(),
    onToggle: vi.fn(),
    onCreate: vi.fn(),
    onClear: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
  render(<DetectPanel {...props} />);
  return props;
}

describe("DetectPanel", () => {
  beforeEach(() => {
    vi.mocked(api.detect).mockReset();
  });

  it("sem foto, o botão avisa e fica desabilitado", () => {
    setup({ hasPhoto: false });
    const btn = screen.getByRole("button", { name: "Envie a foto primeiro" });
    expect(btn).toBeDisabled();
  });

  it("com foto, clicar em 'Detectar na foto' chama a API e devolve os candidatos", async () => {
    vi.mocked(api.detect).mockResolvedValue({ candidates: CANDIDATOS });
    const props = setup({ hasPhoto: true });

    await userEvent.click(screen.getByRole("button", { name: "Detectar na foto" }));

    expect(api.detect).toHaveBeenCalledWith("n1", 0.5);
    expect(props.onResult).toHaveBeenCalledWith(CANDIDATOS);
  });

  it("detecção sem resultado avisa o operador (não é erro de rede)", async () => {
    vi.mocked(api.detect).mockResolvedValue({ candidates: [] });
    const props = setup({ hasPhoto: true });

    await userEvent.click(screen.getByRole("button", { name: "Detectar na foto" }));

    expect(props.onError).toHaveBeenCalledWith(expect.stringMatching(/sensibilidade/));
  });

  it("lista os candidatos com checkbox refletindo `selected`, e marcar/desmarcar chama onToggle", async () => {
    const props = setup({ candidates: CANDIDATOS, selected: new Set([0]) });

    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[0]).toHaveAttribute("data-state", "checked");
    expect(checkboxes[1]).toHaveAttribute("data-state", "unchecked");

    await userEvent.click(checkboxes[1]);
    expect(props.onToggle).toHaveBeenCalledWith(1);
  });

  it("'Criar N superfícies' fica desabilitado sem seleção e habilita com seleção", () => {
    const { rerender } = render(
      <DetectPanel
        nodeId="n1"
        hasPhoto
        candidates={CANDIDATOS}
        selected={new Set()}
        onResult={() => {}}
        onToggle={() => {}}
        onCreate={() => {}}
        onClear={() => {}}
        onError={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Criar 0 superfícies/ })).toBeDisabled();

    rerender(
      <DetectPanel
        nodeId="n1"
        hasPhoto
        candidates={CANDIDATOS}
        selected={new Set([0])}
        onResult={() => {}}
        onToggle={() => {}}
        onCreate={() => {}}
        onClear={() => {}}
        onError={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Criar 1 superfície$/ })).toBeEnabled();
  });

  it("'Limpar' só aparece com candidatos, e chama onClear", async () => {
    const props = setup({ candidates: CANDIDATOS });
    const limpar = screen.getByRole("button", { name: "Limpar" });
    await userEvent.click(limpar);
    expect(props.onClear).toHaveBeenCalled();
  });

  it("sem candidatos, 'Limpar' não aparece", () => {
    setup({ candidates: [] });
    expect(screen.queryByRole("button", { name: "Limpar" })).not.toBeInTheDocument();
  });
});
