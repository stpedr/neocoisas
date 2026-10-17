import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RemotePage from "./page";
import { api } from "../lib/api";
import type { Project, Surface } from "../lib/types";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    adoptTokenFromHash: vi.fn(),
    api: {
      ...actual.api,
      health: vi.fn(),
      getProject: vi.fn(),
      createSurface: vi.fn(),
      fullscreenSurface: vi.fn(),
      colorPresets: vi.fn().mockResolvedValue({ presets: [] }),
      mediaThumbUrl: (sha: string) => `/media/${sha}/thumb`,
    },
  };
});

const COLOR = { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 };

function surface(id: string, label: string): Surface {
  return {
    id, label, node_id: "n1", z: 0, visible: true, polygon_src: null,
    warp: { type: "homography", base: [[100, 100], [400, 100], [400, 300], [100, 300]] },
    source: { kind: "test", media: null, color: [255, 255, 255], fit: "stretch", loop: true, speed: 1, offset_s: 0 },
    opacity: 1, feather: 0, blend_mode: "normal", layers: [], color: COLOR,
  };
}

function project(surfaces: Surface[]): Project {
  return {
    version: 1, name: "Show", fps: 30, media: {}, looks: [], surfaces,
    nodes: [{
      id: "n1", name: "Projetor", photo: null, photo_boundary: [],
      output: { width: 1920, height: 1080, intensity: 1, blackout: false, pattern: "none", show_outlines: false,
                latency_ms: 0, color: COLOR, flip_h: false, flip_v: false },
    }],
  };
}

async function openSurfacesTab() {
  render(<RemotePage />);
  await userEvent.click(await screen.findByRole("button", { name: "Superfícies" }));
}

describe("remote no celular — superfícies", () => {
  beforeEach(() => {
    vi.mocked(api.health).mockResolvedValue({ ok: true, version: "1", revision: 1 });
    vi.mocked(api.getProject).mockResolvedValue({ revision: 1, project: project([surface("s1", "Parede")]) });
  });

  it("'+ Nova superfície' cria outra superfície no projetor atual", async () => {
    vi.mocked(api.createSurface).mockResolvedValue({
      revision: 2, project: project([surface("s1", "Parede"), surface("s2", "Superfície 2")]), surface_id: "s2",
    });
    await openSurfacesTab();

    await userEvent.click(screen.getByRole("button", { name: "+ Nova superfície" }));

    expect(api.createSurface).toHaveBeenCalledWith("n1", false);
    expect(await screen.findByText("Superfície 2")).toBeInTheDocument();
  });

  it("'+ Tela cheia' cria uma superfície ocupando a saída inteira", async () => {
    vi.mocked(api.createSurface).mockResolvedValue({ revision: 2, project: project([surface("s1", "Parede")]), surface_id: "s1" });
    await openSurfacesTab();
    await userEvent.click(screen.getByRole("button", { name: "+ Tela cheia" }));
    expect(api.createSurface).toHaveBeenCalledWith("n1", true);
  });

  it("sem superfícies, o botão de criar continua lá (não depende do editor)", async () => {
    vi.mocked(api.getProject).mockResolvedValue({ revision: 1, project: project([]) });
    await openSurfacesTab();
    expect(screen.getByRole("button", { name: "+ Nova superfície" })).toBeInTheDocument();
  });

  it("cada superfície tem 'Tela cheia' para mapear na saída inteira", async () => {
    vi.mocked(api.fullscreenSurface).mockResolvedValue({ revision: 2, project: project([surface("s1", "Parede")]) });
    await openSurfacesTab();
    await userEvent.click(screen.getByRole("button", { name: "Tela cheia: Parede" }));
    expect(api.fullscreenSurface).toHaveBeenCalledWith("s1");
  });
});
