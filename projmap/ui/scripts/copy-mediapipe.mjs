// Copia o runtime WASM do MediaPipe para public/ (vira out/mediapipe/wasm no build).
// Assim a página /sensor do celular carrega tudo do próprio mestre — funciona sem
// internet (o modelo do rosto também pode ser local: python -m projmap.tools.fetch_models).
import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";

const src = "node_modules/@mediapipe/tasks-vision/wasm";
const dst = "public/mediapipe/wasm";
if (!existsSync(src)) {
  console.warn("[copy-mediapipe] @mediapipe/tasks-vision ausente; rode npm ci");
  process.exit(0);
}
mkdirSync(dst, { recursive: true });
// Só as variantes clássicas (com e sem SIMD); as "module" não são usadas.
for (const f of readdirSync(src).filter((f) => f.startsWith("vision_wasm_internal") || f.startsWith("vision_wasm_nosimd_internal"))) {
  cpSync(join(src, f), join(dst, f));
}
console.log("[copy-mediapipe] wasm copiado para", dst);
