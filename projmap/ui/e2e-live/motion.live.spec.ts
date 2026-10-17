import { expect, test } from "@playwright/test";

// Passo de UI do e2e ao vivo: o operador adiciona um motion (.html) a uma
// superfície, liga a entrada de vídeo do motion e mapeia em tela cheia.
const SURFACE = process.env.PROJMAP_LIVE_SURFACE_LABEL ?? "Superfície 1";
const MOTION_FILE = process.env.PROJMAP_LIVE_MOTION_FILE ?? "";

test.setTimeout(120_000);

test("adiciona um motion HTML a uma superfície, com entrada de vídeo, em tela cheia", async ({ page }) => {
  expect(MOTION_FILE, "defina PROJMAP_LIVE_MOTION_FILE").not.toBe("");
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(SURFACE) }).first().click();

  await page.getByLabel("+ Motion").setInputFiles(MOTION_FILE);
  await expect(page.getByLabel("Fonte")).toHaveText(/Motion \(HTML\)/);

  await page.getByLabel("Entrada de vídeo do motion").fill("auto");

  await page.getByText("Cantos (px do projetor)").click();
  await page.getByRole("button", { name: "Tela cheia", exact: true }).click();
  await expect(page.getByLabel("TL x")).toHaveValue("0", { timeout: 15_000 });
  await expect(page.getByLabel("BR x")).toHaveValue("1920", { timeout: 15_000 });
  await expect(page.getByText("Salvo")).toBeVisible({ timeout: 20_000 });
});
