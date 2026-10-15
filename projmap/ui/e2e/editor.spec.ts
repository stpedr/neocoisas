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
    surfaces: [],
    media: {},
    looks: [],
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/project", (route) =>
    route.fulfill({ json: PROJECT_PAYLOAD }),
  );
});

test("o editor carrega com o nome do projeto e os atalhos de topo visíveis", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByLabel("Nome do projeto")).toBeVisible();
  await expect(page.getByRole("group", { name: "Saída do projetor" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Mídias/ })).toBeVisible();
});
