import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import LayersPanel from "./LayersPanel";
import type { Layer, MediaItem, Project, Surface } from "../lib/types";
import { DEFAULT_SOURCE } from "../lib/types";

const VIDEO: MediaItem = {
  sha256: "v1",
  filename: "clip.mp4",
  ext: "mp4",
  kind: "video",
  size_bytes: 2048,
  width: 1920,
  height: 1080,
};

function makeLayer(id: string, label: string, overrides: Partial<Layer> = {}): Layer {
  return {
    id,
    label,
    visible: true,
    source: { ...DEFAULT_SOURCE, kind: "test" },
    rect: [0.25, 0.25, 0.5, 0.5],
    opacity: 1,
    ...overrides,
  };
}

function makeSurface(layers: Layer[] = []): Surface {
  return {
    id: "s1",
    label: "Fachada",
    node_id: "n1",
    z: 0,
    visible: true,
    polygon_src: null,
    warp: {
      type: "homography",
      base: [
        [0, 0],
        [1920, 0],
        [1920, 1080],
        [0, 1080],
      ],
    },
    source: { ...DEFAULT_SOURCE, kind: "test" },
    opacity: 1,
    feather: 0,
    blend_mode: "normal",
    layers,
    color: { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 },
  };
}

function makeProject(): Project {
  return {
    version: 1,
    name: "Show",
    fps: 30,
    nodes: [],
    surfaces: [],
    media: { v1: VIDEO },
    looks: [],
  };
}

function Harness({
  initialLayers = [],
  initialSelected = null,
}: {
  initialLayers?: Layer[];
  initialSelected?: string | null;
}) {
  const [s, setS] = useState(() => makeSurface(initialLayers));
  const [selId, setSelId] = useState<string | null>(initialSelected);
  return (
    <LayersPanel
      surface={s}
      project={makeProject()}
      selectedLayerId={selId}
      onSelectLayer={setSelId}
      onChange={(fn) => setS(fn)}
      onUpload={vi.fn().mockResolvedValue(VIDEO)}
      onError={vi.fn()}
      onOpenGallery={(pick) => pick(VIDEO)}
    />
  );
}

describe("LayersPanel", () => {
  it("mostra 'só o fundo' quando não há camadas e adiciona '+ Cartela' selecionando-a", async () => {
    render(<Harness />);
    expect(screen.getByText("só o fundo")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "+ Cartela" }));

    expect(screen.getByText("1 por cima do fundo")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveValue("Cartela");
  });

  it("renderiza o topo da lista como a última camada (frente) e ▲/▼ trocam a ordem", async () => {
    const l1 = makeLayer("camada-1", "Fundo extra");
    const l2 = makeLayer("camada-2", "Logo topo");
    render(<Harness initialLayers={[l1, l2]} />);

    // Topo da lista = último elemento do array (camada-2 na frente de camada-1)
    const itemsBefore = screen.getAllByRole("listitem");
    expect(itemsBefore).toHaveLength(2);
    expect(within(itemsBefore[0]).getByText(/Logo topo/)).toBeInTheDocument();
    expect(within(itemsBefore[1]).getByText(/Fundo extra/)).toBeInTheDocument();

    // Clicar ▲ ("Para frente") em "Fundo extra" (índice 0 no array) move para índice 1 (topo da lista visual)
    await userEvent.click(within(itemsBefore[1]).getByTitle("Para frente"));

    const itemsAfterUp = screen.getAllByRole("listitem");
    expect(within(itemsAfterUp[0]).getByText(/Fundo extra/)).toBeInTheDocument();
    expect(within(itemsAfterUp[1]).getByText(/Logo topo/)).toBeInTheDocument();

    // Clicar ▼ ("Para trás") em "Fundo extra" (agora no topo) devolve para trás
    await userEvent.click(within(itemsAfterUp[0]).getByTitle("Para trás"));

    const itemsAfterDown = screen.getAllByRole("listitem");
    expect(within(itemsAfterDown[0]).getByText(/Logo topo/)).toBeInTheDocument();
    expect(within(itemsAfterDown[1]).getByText(/Fundo extra/)).toBeInTheDocument();
  });

  it("alterna visibilidade da camada pelo checkbox", async () => {
    const l1 = makeLayer("camada-1", "Logo");
    const onChange = vi.fn();
    render(
      <LayersPanel
        surface={makeSurface([l1])}
        project={makeProject()}
        selectedLayerId={null}
        onSelectLayer={vi.fn()}
        onChange={onChange}
        onUpload={vi.fn()}
        onError={vi.fn()}
        onOpenGallery={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("checkbox"));
    const reducer = onChange.mock.calls.at(-1)![0];
    const next = reducer(makeSurface([l1]));
    expect(next.layers[0].visible).toBe(false);
  });

  it("adiciona camada '+ Da galeria' com o item escolhido", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "+ Da galeria" }));

    expect(screen.getByLabelText("Nome")).toHaveValue("clip.mp4");
  });

  it("edita Nome, Ajuste, Preencher superfície e Remover camada na camada selecionada", async () => {
    const l1 = makeLayer("camada-1", "Logo");
    render(<Harness initialLayers={[l1]} initialSelected="camada-1" />);

    const nome = screen.getByLabelText("Nome");
    await userEvent.clear(nome);
    await userEvent.type(nome, "Patrocínio");
    expect(nome).toHaveValue("Patrocínio");

    await userEvent.click(screen.getByRole("button", { name: "Preencher superfície" }));
    expect(screen.getByLabelText("X %")).toHaveValue(0);
    expect(screen.getByLabelText("Larg. %")).toHaveValue(100);

    await userEvent.click(screen.getByRole("button", { name: "Remover camada" }));
    expect(screen.getByText("só o fundo")).toBeInTheDocument();
    expect(screen.queryByLabelText("Nome")).not.toBeInTheDocument();
  });

  it("ajusta a Opacidade da camada pelo teclado (ArrowLeft no Slider)", () => {
    const l1 = makeLayer("camada-1", "Logo", { opacity: 0.8 });
    const onChange = vi.fn();
    render(
      <LayersPanel
        surface={makeSurface([l1])}
        project={makeProject()}
        selectedLayerId="camada-1"
        onSelectLayer={vi.fn()}
        onChange={onChange}
        onUpload={vi.fn()}
        onError={vi.fn()}
        onOpenGallery={vi.fn()}
      />,
    );

    const slider = screen.getByRole("slider", { name: /Opacidade/i });
    slider.focus();
    fireEvent.keyDown(slider, { key: "ArrowLeft" });

    expect(onChange).toHaveBeenCalled();
    const next = onChange.mock.calls.at(-1)![0](makeSurface([l1]));
    expect(next.layers[0].opacity).toBeCloseTo(0.79, 2);
  });
});
