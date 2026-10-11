// Copia o decodificador de QR (jsQR, UMD) para www/vendor: o lançador é HTML
// puro, sem bundler, e precisa funcionar offline.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(join(root, "www", "vendor"), { recursive: true });
copyFileSync(join(root, "node_modules", "jsqr", "dist", "jsQR.js"), join(root, "www", "vendor", "jsQR.js"));
console.log("jsQR copiado para www/vendor/");
