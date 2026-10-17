import { expect, test } from "@playwright/test";

// Smoke test: o editor exige falar com o mestre (FastAPI) assim que carrega
// — "Não foi possível falar com o mestre" aparece sem ele (descoberto rodando
// este teste contra o `next dev` puro). Por isso GET /api/project é mockado
// aqui: o objetivo deste teste é validar o shell da UI, não a integração com
// o backend real (essa fica pros testes que sobem o mestre de verdade).

const PROJECT_PAYLOAD = {
  revision: 1,
  project: {
    version: 1,
    name: "Natal na fachada",
    fps: 30,
    nodes: [
      {
        id: "n1",
        name: "Principal",
        output: {
          width: 1920,
          height: 1080,
          intensity: 1,
          blackout: false,
          pattern: "none",
          show_outlines: false,
          latency_ms: 0,
          color: { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 },
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
        source: {
          kind: "test",
          media: null,
          color: [255, 255, 255],
          fit: "stretch",
          loop: true,
          speed: 1,
          offset_s: 0,
        },
        opacity: 1,
        feather: 0,
        blend_mode: "normal",
        layers: [
          {
            id: "camada-1",
            label: "Fundo extra",
            visible: true,
            source: {
              kind: "test",
              media: null,
              color: [255, 255, 255],
              fit: "stretch",
              loop: true,
              speed: 1,
              offset_s: 0,
            },
            rect: [0.1, 0.1, 0.5, 0.5],
            opacity: 1,
          },
          {
            id: "camada-2",
            label: "Logo topo",
            visible: true,
            source: {
              kind: "test",
              media: null,
              color: [255, 255, 255],
              fit: "stretch",
              loop: true,
              speed: 1,
              offset_s: 0,
            },
            rect: [0.2, 0.2, 0.4, 0.4],
            opacity: 1,
          },
        ],
        color: { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 },
      },
    ],
    media: {},
    looks: [],
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/project", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({ json: { revision: 2 } });
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
  await page.route("**/api/suggest", (route) =>
    route.fulfill({ json: { media_count: 0, suggestions: {} } }),
  );
});

test("o editor carrega com o nome do projeto e os atalhos de topo visíveis", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByLabel("Nome do projeto")).toBeVisible();
  await expect(page.getByRole("group", { name: "Saída do projetor" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Mídias/ })).toBeVisible();
});

test("reordena camadas com ▲/▼ e abre a galeria como Dialog", async ({ page }) => {
  await page.goto("/");

  // Selecionar a superfície na lista
  await page.getByRole("button", { name: /Parede principal/ }).click();

  // Verificar que as duas camadas aparecem com "Logo topo" na frente (primeiro item da lista)
  const layersSection = page.locator("div", { hasText: "2 por cima do fundo" }).first();
  await expect(layersSection).toBeVisible();

  const items = page.locator("li", { has: page.getByTitle("Para frente") });
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("Logo topo");
  await expect(items.nth(1)).toContainText("Fundo extra");

  // Mover "Fundo extra" para frente (▲)
  await items.nth(1).getByTitle("Para frente").click();
  await expect(items.nth(0)).toContainText("Fundo extra");
  await expect(items.nth(1)).toContainText("Logo topo");

  // Abrir a galeria (+ Da galeria) e fechar com Escape
  await page.getByRole("button", { name: "+ Da galeria" }).click();
  const dialog = page.getByRole("dialog", { name: /Camada em "Parede principal"/ });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});
