import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MediaGallery from "./MediaGallery";
import SuggestAll from "./SuggestAll";
import { api } from "../lib/api";
import type { LibraryItem, MediaInfo, Surface } from "../lib/types";
import { DEFAULT_SOURCE } from "../lib/types";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      mediaInfo: vi.fn(),
      library: vi.fn(),
      suggest: vi.fn(),
      importLibrary: vi.fn(),
      mediaThumbUrl: (sha: string) => `/media/${sha}/thumb`,
      libraryThumbUrl: (id: string) => `/lib/${id}/thumb`,
    },
  };
});

const PROJ_VIDEO: MediaInfo = {
  sha256: "sha-video-1",
  filename: "abertura.mp4",
  ext: "mp4",
  kind: "video",
  size_bytes: 5000,
  width: 1920,
  height: 1080,
  duration: 12,
  aspect: 16 / 9,
};

const PROJ_IMAGE: MediaInfo = {
  sha256: "sha-img-1",
  filename: "logo.png",
  ext: "png",
  kind: "image",
  size_bytes: 1200,
  width: 800,
  height: 800,
  duration: 0,
  aspect: 1,
};

const LIB_GIF: LibraryItem = {
  id: "lib-1",
  name: "fogo.gif",
  folder: "Efeitos",
  kind: "gif",
  size_bytes: 900,
  width: 640,
  height: 480,
  duration: 3,
  aspect: 4 / 3,
};

describe("MediaGallery", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.mediaInfo).mockResolvedValue({ items: [PROJ_VIDEO, PROJ_IMAGE] });
    vi.mocked(api.library).mockResolvedValue({
      roots: [{ path: "C:/Midias", exists: true }],
      can_edit_roots: true,
      folders: ["Efeitos"],
      items: [LIB_GIF],
    });
    vi.mocked(api.suggest).mockResolvedValue({
      media_count: 3,
      suggestions: {
        s1: {
          pick: { ref: "sha:sha-video-1", name: "abertura.mp4", kind: "video", score: 0.95, reasons: ["Proporção 16:9 exata"] },
          ranking: [{ ref: "sha:sha-video-1", name: "abertura.mp4", kind: "video", score: 0.95, reasons: ["Proporção 16:9 exata"] }],
        },
      },
    });
    vi.mocked(api.importLibrary).mockResolvedValue({
      item: {
        sha256: "sha-imported-gif",
        filename: "fogo.gif",
        ext: "gif",
        kind: "gif",
        size_bytes: 900,
      },
    });
  });

  it("não renderiza o diálogo quando open=false", () => {
    render(<MediaGallery open={false} onPick={vi.fn()} onClose={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lista mídias do projeto, filtra por busca/tipo e escolhe um item chamando onPick + onClose", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <MediaGallery
        open={true}
        title="Mídia da parede"
        onPick={onPick}
        onClose={onClose}
        onError={vi.fn()}
      />,
    );

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByText("abertura.mp4")).toBeInTheDocument();
    expect(screen.getByText("logo.png")).toBeInTheDocument();

    // Filtrar por tipo "Foto"
    await userEvent.click(screen.getByRole("button", { name: "Foto" }));
    expect(screen.queryByText("abertura.mp4")).not.toBeInTheDocument();
    expect(screen.getByText("logo.png")).toBeInTheDocument();

    // Voltar para "Tudo" e filtrar por nome
    await userEvent.click(screen.getByRole("button", { name: "Tudo" }));
    await userEvent.type(screen.getByPlaceholderText("Buscar pelo nome…"), "abertura");
    expect(screen.getByText("abertura.mp4")).toBeInTheDocument();
    expect(screen.queryByText("logo.png")).not.toBeInTheDocument();

    // Escolher o item
    await userEvent.click(screen.getByText("abertura.mp4"));
    await waitFor(() => expect(onPick).toHaveBeenCalledWith(PROJ_VIDEO));
    expect(onClose).toHaveBeenCalled();
  });

  it("importa item da aba 'Minhas pastas' e mostra sugestões quando surfaceId é informado", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <MediaGallery
        open={true}
        surfaceId="s1"
        onPick={onPick}
        onClose={onClose}
        onError={vi.fn()}
      />,
    );

    expect(await screen.findByText(/Sugeridas para esta superfície/)).toBeInTheDocument();
    expect(screen.getByText("Proporção 16:9 exata")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Minhas pastas/ }));
    expect(await screen.findByText("fogo.gif")).toBeInTheDocument();

    await userEvent.click(screen.getByText("fogo.gif"));
    await waitFor(() => expect(api.importLibrary).toHaveBeenCalledWith("lib-1"));
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ sha256: "sha-imported-gif" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("fecha ao clicar em Fechar ou apertar Escape", async () => {
    const onClose = vi.fn();
    render(<MediaGallery open={true} onPick={vi.fn()} onClose={onClose} onError={vi.fn()} />);

    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("SuggestAll", () => {
  const S1: Surface = {
    id: "s1",
    label: "Coluna",
    node_id: "n1",
    z: 0,
    visible: true,
    polygon_src: null,
    warp: { type: "homography", base: [[0, 0], [100, 0], [100, 100], [0, 100]] },
    source: { ...DEFAULT_SOURCE, kind: "test" },
    opacity: 1,
    feather: 0,
    blend_mode: "normal",
    layers: [],
    color: { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 },
  };

  beforeEach(() => {
    vi.mocked(api.mediaInfo).mockResolvedValue({ items: [PROJ_VIDEO] });
    vi.mocked(api.suggest).mockResolvedValue({
      media_count: 1,
      suggestions: {
        s1: {
          pick: { ref: "sha:sha-video-1", name: "abertura.mp4", kind: "video", score: 0.95, reasons: ["16:9"] },
          ranking: [],
        },
      },
    });
  });

  it("mostra a sugestão por superfície e aplica nas marcadas", async () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(<SuggestAll open={true} surfaces={[S1]} onApply={onApply} onClose={onClose} onError={vi.fn()} />);

    expect(await screen.findByText("abertura.mp4")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Aplicar em 1 superfície/ }));

    await waitFor(() =>
      expect(onApply).toHaveBeenCalledWith([{ surfaceId: "s1", item: PROJ_VIDEO }]),
    );
    expect(onClose).toHaveBeenCalled();
  });
});
