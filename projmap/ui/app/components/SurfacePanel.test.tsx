import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SurfacePanel from "./SurfacePanel";
import { api } from "../lib/api";
import type { MediaItem, Project, Surface } from "../lib/types";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      colorPresets: vi.fn().mockResolvedValue({ presets: [] }),
      mediaThumbUrl: (sha: string) => `/media/${sha}/thumb`,
    },
  };
});

const VIDEO: MediaItem = { sha256: "v1", filename: "fundo.mp4", ext: "mp4", kind: "video", size_bytes: 1000 };

function surface(overrides: Partial<Surface> = {}): Surface {
  return {
    id: "s1",
    label: "Parede",
    node_id: "n1",
    z: 0,
    visible: true,
    polygon_src: null,
    warp: {
      type: "homography",
      base: [
        [0, 0],
        [100, 0],
        [100, 100],
        [0, 100],
      ],
    },
    source: { kind: "video", media: "v1", color: [255, 255, 255], fit: "stretch", loop: true, speed: 1, offset_s: 0 },
    opacity: 1,
    feather: 0,
    blend_mode: "normal",
    layers: [],
    color: { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 },
    ...overrides,
  };
}

function project(overrides: Partial<Project> = {}): Project {
  return {
    version: 1,
    name: "Demo",
    fps: 30,
    nodes: [],
    surfaces: [],
    media: { v1: VIDEO },
    looks: [],
    ...overrides,
  };
}

function setup(overrides: Partial<React.ComponentProps<typeof SurfacePanel>> = {}) {
  const onChange = vi.fn();
  const props = {
    surface: surface(),
    project: project(),
    onChange,
    onDelete: vi.fn(),
    onUpload: vi.fn(),
    onError: vi.fn(),
    onOpenGallery: vi.fn(),
    ...overrides,
  };
  render(<SurfacePanel {...props} />);
  return { ...props, onChange };
}

describe("SurfacePanel", () => {
  beforeEach(() => {
    vi.mocked(api.colorPresets).mockClear();
  });

  it("editar o Nome chama onChange e o campo controlado reflete o texto digitado", async () => {
    // Campo controlado: sem um estado real por trás, "limpar + digitar" luta
    // contra o próprio valor do prop a cada tecla. Esse wrapper replica o que
    // page.tsx faz de verdade (aplica o reducer de volta na superfície).
    function Harness() {
      const [s, setS] = useState(surface());
      return (
        <SurfacePanel
          surface={s}
          project={project()}
          onChange={(fn) => setS(fn)}
          onDelete={() => {}}
          onUpload={vi.fn()}
          onError={() => {}}
          onOpenGallery={() => {}}
        />
      );
    }
    render(<Harness />);

    const nome = screen.getByLabelText("Nome");
    await userEvent.clear(nome);
    await userEvent.type(nome, "Igreja");

    expect(nome).toHaveValue("Igreja");
  });

  it("desmarcar Visível chama onChange com visible:false", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("checkbox", { name: "Visível" }));

    const fn = props.onChange.mock.calls.at(-1)![0];
    expect(fn(surface()).visible).toBe(false);
  });

  it("trocar a Fonte para um tipo que já tem mídia no projeto aplica na hora", async () => {
    const props = setup({ project: project({ media: { v1: VIDEO, g1: { ...VIDEO, sha256: "g1", kind: "gif", filename: "a.gif" } } }) });

    await userEvent.click(screen.getByLabelText("Fonte"));
    await userEvent.click(await screen.findByRole("option", { name: "GIF animado" }));

    const fn = props.onChange.mock.calls.at(-1)![0];
    const next = fn(surface());
    expect(next.source.kind).toBe("gif");
    expect(next.source.media).toBe("g1");
  });

  it("trocar a Fonte para um tipo de mídia sem nenhum arquivo no projeto NÃO aplica ainda (espera o upload)", async () => {
    // surface() sem mídia nenhuma ainda (fonte "cor", por ex.) é o caso real em
    // que o aviso faz sentido — com s.source.media já preenchido (outro kind), o
    // componente propositalmente não avisa: a mídia antiga continua valendo.
    const props = setup({
      surface: surface({ source: { kind: "color", media: null, color: [0, 0, 0], fit: "stretch", loop: true, speed: 1, offset_s: 0 } }),
      project: project({ media: { v1: VIDEO } }), // sem nenhum .image
    });

    await userEvent.click(screen.getByLabelText("Fonte"));
    await userEvent.click(await screen.findByRole("option", { name: "Imagem" }));

    expect(props.onChange).not.toHaveBeenCalled();
    expect(await screen.findByText(/Nenhum arquivo deste tipo no projeto ainda/)).toBeInTheDocument();
  });

  it("mover a Opacidade pelo teclado chama onChange", async () => {
    const props = setup();
    const op = screen.getByRole("slider", { name: /Opacidade/ });
    op.focus();
    await userEvent.keyboard("{ArrowLeft}");

    const fn = props.onChange.mock.calls.at(-1)![0];
    expect(fn(surface()).opacity).toBeLessThan(1);
  });

  it("trocar o Ajuste chama onChange com o fit novo", async () => {
    const props = setup();
    await userEvent.click(screen.getByLabelText("Ajuste"));
    await userEvent.click(await screen.findByRole("option", { name: "Preencher (corta)" }));

    const fn = props.onChange.mock.calls.at(-1)![0];
    expect(fn(surface()).source.fit).toBe("cover");
  });

  it("trocar a Mistura chama onChange com o blend_mode novo", async () => {
    const props = setup();
    await userEvent.click(screen.getByLabelText("Mistura"));
    await userEvent.click(await screen.findByRole("option", { name: "Somar (luz)" }));

    const fn = props.onChange.mock.calls.at(-1)![0];
    expect(fn(surface()).blend_mode).toBe("add");
  });

  it("canto com valor válido chama onChange com o warp atualizado", async () => {
    const props = setup();
    const tlX = screen.getByLabelText("TL x");
    await userEvent.clear(tlX);
    await userEvent.type(tlX, "5");

    const fn = props.onChange.mock.calls.at(-1)![0];
    expect(fn(surface()).warp.base[0]).toEqual([5, 0]);
    expect(props.onError).not.toHaveBeenCalled();
  });

  it("canto que vira quad côncavo/cruzado é recusado: onError, sem onChange", async () => {
    // Empurra TL bem pra dentro do quad (equivalente ao dardo testado em geometry.test.ts) — fica côncavo.
    const props = setup({
      surface: surface({
        warp: { type: "homography", base: [[0, 0], [10, 0], [10, 10], [5, 3]] },
      }),
    });
    const trX = screen.getByLabelText("TR x");
    // mexe no TR de um jeito que não desfaz a concavidade (qualquer edição aqui já reavalia o quad inteiro)
    await userEvent.clear(trX);
    await userEvent.type(trX, "10");

    expect(props.onError).toHaveBeenCalledWith(expect.stringMatching(/Canto recusado/));
    expect(props.onChange).not.toHaveBeenCalled();
  });

  it("'Excluir superfície' chama onDelete", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("button", { name: /Excluir superfície/ }));
    expect(props.onDelete).toHaveBeenCalled();
  });
});
