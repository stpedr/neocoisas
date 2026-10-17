import { expect, test, type Page } from "@playwright/test";

// Fluxo das entradas ao vivo no editor: trocar a fonte para "Entrada de vídeo",
// adicionar um efeito de áudio e mapear em tela cheia. O mestre é mockado (como
// em editor.spec.ts); o que se confere é o projeto que o editor manda no PUT.

const COLOR = { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 };

const PROJECT_PAYLOAD = {
  revision: 1,
  project: {
    version: 1,
    name: "Show ao vivo",
    fps: 30,
    nodes: [
      {
        id: "n1",
        name: "Projetor",
        output: {
          width: 1920,
          height: 1080,
          intensity: 1,
          blackout: false,
          pattern: "none",
          show_outlines: false,
          latency_ms: 0,
          color: COLOR,
          flip_h: false,
          flip_v: false,
        },
        photo: null,
        photo_boundary: [],
      },
    ],
    surfaces: [
      {
        id: "s1",
        label: "Parede principal",
        node_id: "n1",
        z: 0,
        visible: true,
        polygon_src: null,
        warp: {
          type: "homography",
          base: [
            [100, 100],
            [900, 100],
            [900, 600],
            [100, 600],
          ],
        },
        source: { kind: "test", media: null, color: [255, 255, 255], fit: "stretch", loop: true, speed: 1, offset_s: 0 },
        opacity: 1,
        feather: 0,
        blend_mode: "normal",
        layers: [],
        color: COLOR,
        fx: [],
      },
    ],
    media: {},
    looks: [],
    audio: { device: "loopback", gain: 1 },
  },
};

interface SentSurface {
  source: { kind: string; media: string | null; device?: string | null };
  fx?: { type: string; band: string; amount: number; enabled: boolean }[];
  warp: { base: number[][] };
}

function trackPuts(page: Page) {
  const puts: SentSurface[] = [];
  page.on("request", (req) => {
    if (req.method() === "PUT" && req.url().endsWith("/api/project")) {
      const body = req.postDataJSON() as { project: { surfaces: SentSurface[] } };
      puts.push(body.project.surfaces[0]);
    }
  });
  return () => puts.at(-1);
}

test.beforeEach(async ({ page }) => {
  let revision = 1;
  await page.route("**/api/project", async (route) => {
    if (route.request().method() === "PUT") {
      revision += 1;
      await route.fulfill({ json: { revision } });
    } else {
      await route.fulfill({ json: PROJECT_PAYLOAD });
    }
  });
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok", revision: 1 } }));
  await page.route("**/api/color-presets", (route) => route.fulfill({ json: { presets: [] } }));
  await page.route("**/api/media/info", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/library*", (route) =>
    route.fulfill({ json: { roots: [], can_edit_roots: false, folders: [], items: [] } }),
  );
  await page.route("**/api/suggest", (route) => route.fulfill({ json: { media_count: 0, suggestions: {} } }));
});

test("entrada de vídeo + efeito de áudio + tela cheia chegam ao mestre", async ({ page }) => {
  const lastSurface = trackPuts(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Parede principal/ }).click();

  // 1) Fonte = Entrada de vídeo (sem mídia, dispositivo "auto")
  await page.getByLabel("Fonte").click();
  await page.getByRole("option", { name: "Entrada de vídeo (câmera/captura)" }).click();
  await expect(page.getByLabel("Dispositivo")).toHaveValue("auto");
  await expect.poll(() => lastSurface()?.source).toMatchObject({ kind: "capture", media: null, device: "auto" });

  // 2) Efeito de áudio: flash na batida
  await page.getByText("Efeitos de áudio", { exact: true }).click();
  await page.getByRole("button", { name: "+ Efeito" }).click();
  await page.getByRole("combobox", { name: "Efeito 1", exact: true }).click();
  await page.getByRole("option", { name: "Flash (strobe)" }).click();
  await page.getByRole("combobox", { name: "Reage a 1", exact: true }).click();
  await page.getByRole("option", { name: "Batida" }).click();
  await expect(page.getByText("Efeitos de áudio · 1")).toBeVisible();
  await expect.poll(() => lastSurface()?.fx).toEqual([{ type: "strobe", band: "beat", amount: 0.5, enabled: true }]);

  // 3) Tela cheia: o quad vira a saída inteira do projetor
  await page.getByText("Cantos (px do projetor)").click();
  await page.getByRole("button", { name: "Tela cheia", exact: true }).click();
  await expect(page.getByLabel("BR x")).toHaveValue("1920");
  await expect(page.getByLabel("BR y")).toHaveValue("1080");
  await expect.poll(() => lastSurface()?.warp.base).toEqual([
    [0, 0],
    [1920, 0],
    [1920, 1080],
    [0, 1080],
  ]);

  // A fonte e o efeito continuam lá depois do mapeamento
  const final = lastSurface();
  expect(final?.source.kind).toBe("capture");
  expect(final?.fx?.[0]?.type).toBe("strobe");
});
