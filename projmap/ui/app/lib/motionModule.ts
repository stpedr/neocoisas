// Especificação "Motion Module v1" (motion-module/1):
// - Parse e validação estrita de manifesto HTML via DOMParser (sem executar scripts)
// - Biblioteca versionada por (id, version) com detecção de conflito de id
// - Presets nomeados com clamp de range, descarte de params obsoletos e aviso de versão
// - Motor de Áudio Central (AudioContext + AnalyserNode único: bass, mid, high, level, beat)
// - Regras de automação por fase (motion:state) e contagem de beats

export type MotionParamType = "float" | "int" | "bool" | "color" | "select" | "vec3";

export type Vec3 = [number, number, number];
export type MotionParamValue = number | boolean | string | Vec3;

export interface MotionSelectOption {
  value: string;
  label: string;
}

export interface MotionParamDef {
  key: string;
  label: string;
  type: MotionParamType;
  group: string;
  default: MotionParamValue;
  min?: number;
  max?: number;
  step?: number;
  options?: MotionSelectOption[];
}

export interface MotionTriggerDef {
  id: string;
  label: string;
}

export interface MotionModeDef {
  id: string;
  label: string;
}

export interface MotionManifest {
  spec: "motion-module/1";
  id: string;
  name: string;
  version: string;
  description?: string;
  author?: string;
  params: Record<string, MotionParamDef>;
  modes: MotionModeDef[];
  triggers: MotionTriggerDef[];
}

export interface MotionValidationError {
  field: string;
  message: string;
}

export type MotionParseResult =
  | { ok: true; manifest: MotionManifest; html: string }
  | { ok: false; errors: MotionValidationError[] };

export interface MotionLibraryEntry {
  key: string; // `${id}@${version}`
  id: string;
  version: string;
  name: string;
  manifest: MotionManifest;
  html: string;
  importedAt: string;
}

export interface MotionPreset {
  id: string;
  name: string;
  motionId: string;
  motionVersion: string;
  mode: string;
  params: Record<string, unknown>;
  createdAt: string;
}

export interface MotionAudioFrame {
  bass: number;  // 25–140 Hz (0..1)
  mid: number;   // 250–2200 Hz (0..1)
  high: number;  // 4000–12000 Hz (0..1)
  level: number; // RMS / nível geral (0..1)
  beat: number;  // pulso 0..1 (limiar adaptativo com cooldown)
}

export type MotionRule =
  | {
      id: string;
      enabled: boolean;
      kind: "phase_switch";
      whenPhase: string;
      targetMotionKey: string;
    }
  | {
      id: string;
      enabled: boolean;
      kind: "beat_trigger";
      everyNBeats: number;
      triggerId: string;
    };

const VALID_PARAM_TYPES = new Set<MotionParamType>(["float", "int", "bool", "color", "select", "vec3"]);
const HEX_COLOR_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

export function motionKey(id: string, version: string): string {
  return `${id}@${version}`;
}

function isFiniteNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * 1. IMPORTAÇÃO:
 * Lê o manifesto com DOMParser sem executar o arquivo HTML e valida:
 * - spec === "motion-module/1"
 * - id, name e version presentes
 * - cada param com tipo válido (float, int, bool, color, select, vec3) e default dentro de min/max.
 * Se falhar, retorna exatamente qual campo está errado em `errors`.
 */
export function parseAndValidateMotionHtml(html: string): MotionParseResult {
  const errors: MotionValidationError[] = [];
  if (!html || typeof html !== "string" || !html.trim()) {
    return { ok: false, errors: [{ field: "file", message: "Arquivo HTML vazio." }] };
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const scriptEl = doc.querySelector("script#motion-manifest");
  if (!scriptEl) {
    return {
      ok: false,
      errors: [
        {
          field: "motion-manifest",
          message: 'Tag <script type="application/json" id="motion-manifest"> não encontrada no HTML.',
        },
      ],
    };
  }

  const scriptType = (scriptEl.getAttribute("type") ?? "").trim().toLowerCase();
  if (scriptType !== "application/json") {
    errors.push({
      field: "motion-manifest.type",
      message: `Atributo type deve ser "application/json" (recebido: "${scriptType || "vazio"}").`,
    });
  }

  let raw: unknown;
  try {
    raw = JSON.parse(scriptEl.textContent ?? "");
  } catch (e) {
    return {
      ok: false,
      errors: [
        ...errors,
        {
          field: "motion-manifest",
          message: `JSON inválido no manifesto: ${e instanceof Error ? e.message : "erro de sintaxe"}`,
        },
      ],
    };
  }

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {
      ok: false,
      errors: [...errors, { field: "motion-manifest", message: "O manifesto deve ser um objeto JSON." }],
    };
  }

  const obj = raw as Record<string, unknown>;

  if (obj.spec !== "motion-module/1") {
    errors.push({
      field: "spec",
      message: `spec deve ser "motion-module/1" (recebido: ${JSON.stringify(obj.spec ?? null)}).`,
    });
  }

  for (const reqField of ["id", "name", "version"] as const) {
    const val = obj[reqField];
    if (typeof val !== "string" || !val.trim()) {
      errors.push({
        field: reqField,
        message: `Campo obrigatório "${reqField}" deve ser uma string não vazia.`,
      });
    }
  }

  const paramsOut: Record<string, MotionParamDef> = {};
  const rawParams = obj.params ?? {};

  if (rawParams !== undefined && (typeof rawParams !== "object" || rawParams === null)) {
    errors.push({
      field: "params",
      message: "Campo \"params\" deve ser um objeto ou array de definições de parâmetros.",
    });
  } else {
    const entries: [string, unknown][] = Array.isArray(rawParams)
      ? rawParams.map((item, idx) => {
          if (item && typeof item === "object" && !Array.isArray(item)) {
            const rec = item as Record<string, unknown>;
            const k = String(rec.id ?? rec.key ?? rec.name ?? `index_${idx}`).trim();
            return [k, rec];
          }
          return [`index_${idx}`, item];
        })
      : Object.entries(rawParams as Record<string, unknown>);

    for (const [key, rawParam] of entries) {
      const prefix = `params.${key}`;
      if (!key) {
        errors.push({ field: "params", message: "Parâmetro sem chave/id." });
        continue;
      }
      if (!rawParam || typeof rawParam !== "object" || Array.isArray(rawParam)) {
        errors.push({ field: prefix, message: "Definição do parâmetro deve ser um objeto." });
        continue;
      }
      const p = rawParam as Record<string, unknown>;
      const pType = p.type as MotionParamType;
      if (!VALID_PARAM_TYPES.has(pType)) {
        errors.push({
          field: `${prefix}.type`,
          message: `Tipo inválido "${String(p.type)}". Tipos aceitos: float, int, bool, color, select, vec3.`,
        });
        continue;
      }

      const label = typeof p.label === "string" && p.label.trim() ? p.label.trim() : key;
      const group = typeof p.group === "string" && p.group.trim() ? p.group.trim() : "Geral";

      if (pType === "float" || pType === "int") {
        const min = p.min;
        const max = p.max;
        const def = p.default;
        let rangeOk = true;
        if (!isFiniteNum(min)) {
          errors.push({ field: `${prefix}.min`, message: `Campo "${prefix}.min" deve ser numérico.` });
          rangeOk = false;
        }
        if (!isFiniteNum(max)) {
          errors.push({ field: `${prefix}.max`, message: `Campo "${prefix}.max" deve ser numérico.` });
          rangeOk = false;
        }
        if (rangeOk && (min as number) > (max as number)) {
          errors.push({
            field: `${prefix}.min`,
            message: `Campo "${prefix}.min" (${min}) não pode ser maior que max (${max}).`,
          });
          rangeOk = false;
        }
        if (!isFiniteNum(def)) {
          errors.push({
            field: `${prefix}.default`,
            message: `Campo "${prefix}.default" deve ser um número válido.`,
          });
        } else if (pType === "int" && !Number.isInteger(def)) {
          errors.push({
            field: `${prefix}.default`,
            message: `Campo "${prefix}.default" (${def}) deve ser um número inteiro.`,
          });
        } else if (rangeOk && (def < (min as number) || def > (max as number))) {
          errors.push({
            field: `${prefix}.default`,
            message: `Valor default (${def}) fora do intervalo [${min}, ${max}].`,
          });
        } else if (rangeOk) {
          const step = isFiniteNum(p.step) && p.step > 0 ? p.step : pType === "int" ? 1 : 0.01;
          paramsOut[key] = {
            key,
            label,
            type: pType,
            group,
            default: def,
            min: min as number,
            max: max as number,
            step,
          };
        }
      } else if (pType === "bool") {
        if (typeof p.default !== "boolean") {
          errors.push({
            field: `${prefix}.default`,
            message: `Campo "${prefix}.default" deve ser booleano (true ou false).`,
          });
        } else {
          paramsOut[key] = { key, label, type: "bool", group, default: p.default };
        }
      } else if (pType === "color") {
        if (typeof p.default !== "string" || !HEX_COLOR_RE.test(p.default.trim())) {
          errors.push({
            field: `${prefix}.default`,
            message: `Campo "${prefix}.default" deve ser uma cor hexadecimal válida (ex.: #ff00aa).`,
          });
        } else {
          paramsOut[key] = { key, label, type: "color", group, default: normalizeHexColor(p.default.trim()) };
        }
      } else if (pType === "select") {
        if (!Array.isArray(p.options) || p.options.length === 0) {
          errors.push({
            field: `${prefix}.options`,
            message: `Campo "${prefix}.options" deve ser uma lista não vazia de opções.`,
          });
        } else {
          const options: MotionSelectOption[] = [];
          for (let i = 0; i < p.options.length; i++) {
            const opt = p.options[i];
            if (typeof opt === "string" || typeof opt === "number") {
              options.push({ value: String(opt), label: String(opt) });
            } else if (opt && typeof opt === "object" && "value" in opt) {
              const o = opt as Record<string, unknown>;
              options.push({
                value: String(o.value),
                label: typeof o.label === "string" ? o.label : String(o.value),
              });
            } else {
              errors.push({
                field: `${prefix}.options[${i}]`,
                message: `Opção inválida em "${prefix}.options[${i}]".`,
              });
            }
          }
          const defStr = typeof p.default === "string" || typeof p.default === "number" ? String(p.default) : "";
          if (!options.some((o) => o.value === defStr)) {
            errors.push({
              field: `${prefix}.default`,
              message: `Valor default (${JSON.stringify(p.default)}) não está entre as opções de "${prefix}.options".`,
            });
          } else {
            paramsOut[key] = { key, label, type: "select", group, default: defStr, options };
          }
        }
      } else if (pType === "vec3") {
        const min = p.min;
        const max = p.max;
        let rangeOk = true;
        if (!isFiniteNum(min)) {
          errors.push({ field: `${prefix}.min`, message: `Campo "${prefix}.min" deve ser numérico.` });
          rangeOk = false;
        }
        if (!isFiniteNum(max)) {
          errors.push({ field: `${prefix}.max`, message: `Campo "${prefix}.max" deve ser numérico.` });
          rangeOk = false;
        }
        if (rangeOk && (min as number) > (max as number)) {
          errors.push({
            field: `${prefix}.min`,
            message: `Campo "${prefix}.min" (${min}) não pode ser maior que max (${max}).`,
          });
          rangeOk = false;
        }
        const def = p.default;
        if (!Array.isArray(def) || def.length !== 3 || !def.every(isFiniteNum)) {
          errors.push({
            field: `${prefix}.default`,
            message: `Campo "${prefix}.default" deve ser um array numérico de 3 posições [x, y, z].`,
          });
        } else if (rangeOk) {
          const [x, y, z] = def as Vec3;
          const lo = min as number;
          const hi = max as number;
          if (x < lo || x > hi || y < lo || y > hi || z < lo || z > hi) {
            errors.push({
              field: `${prefix}.default`,
              message: `Valor default [${x}, ${y}, ${z}] fora do intervalo [${lo}, ${hi}].`,
            });
          } else {
            const step = isFiniteNum(p.step) && p.step > 0 ? p.step : 0.01;
            paramsOut[key] = {
              key,
              label,
              type: "vec3",
              group,
              default: [x, y, z],
              min: lo,
              max: hi,
              step,
            };
          }
        }
      }
    }
  }

  const modes: MotionModeDef[] = [];
  if (Array.isArray(obj.modes)) {
    obj.modes.forEach((m, i) => {
      if (typeof m === "string" && m.trim()) {
        modes.push({ id: m.trim(), label: m.trim() });
      } else if (m && typeof m === "object" && "id" in m) {
        const mo = m as Record<string, unknown>;
        const id = String(mo.id ?? "").trim();
        if (id) modes.push({ id, label: typeof mo.label === "string" ? mo.label : id });
      } else {
        errors.push({ field: `modes[${i}]`, message: `Modo inválido em modes[${i}].` });
      }
    });
  }

  const triggers: MotionTriggerDef[] = [];
  if (Array.isArray(obj.triggers)) {
    obj.triggers.forEach((t, i) => {
      if (typeof t === "string" && t.trim()) {
        triggers.push({ id: t.trim(), label: t.trim() });
      } else if (t && typeof t === "object" && ("id" in t || "name" in t)) {
        const tr = t as Record<string, unknown>;
        const id = String(tr.id ?? tr.name ?? "").trim();
        if (id) triggers.push({ id, label: typeof tr.label === "string" ? tr.label : id });
      } else {
        errors.push({ field: `triggers[${i}]`, message: `Trigger inválido em triggers[${i}].` });
      }
    });
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }

  const manifest: MotionManifest = {
    spec: "motion-module/1",
    id: (obj.id as string).trim(),
    name: (obj.name as string).trim(),
    version: (obj.version as string).trim(),
    description: typeof obj.description === "string" ? obj.description : undefined,
    author: typeof obj.author === "string" ? obj.author : undefined,
    params: paramsOut,
    modes: modes.length > 0 ? modes : [{ id: "default", label: "Padrão" }],
    triggers,
  };

  return { ok: true, manifest, html };
}

function normalizeHexColor(hex: string): string {
  if (hex.length === 4) {
    const [, r, g, b] = hex;
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
  }
  return hex.slice(0, 7).toLowerCase();
}

/** Valores iniciais de parâmetros a partir do manifesto. */
export function defaultParamsForManifest(manifest: MotionManifest): Record<string, MotionParamValue> {
  const out: Record<string, MotionParamValue> = {};
  for (const [k, def] of Object.entries(manifest.params)) {
    out[k] = Array.isArray(def.default) ? ([...def.default] as Vec3) : def.default;
  }
  return out;
}

/** Agrupa parâmetros pelo atributo `group`. */
export function groupManifestParams(manifest: MotionManifest): Record<string, MotionParamDef[]> {
  const groups: Record<string, MotionParamDef[]> = {};
  for (const def of Object.values(manifest.params)) {
    const g = def.group || "Geral";
    if (!groups[g]) groups[g] = [];
    groups[g].push(def);
  }
  return groups;
}

/**
 * 2. BIBLIOTECA:
 * Verifica se já existe um motion com o mesmo `id` na biblioteca.
 */
export function findExistingById(library: MotionLibraryEntry[], id: string): MotionLibraryEntry[] {
  return library.filter((item) => item.id === id);
}

/**
 * Insere ou atualiza um motion na biblioteca conforme a escolha do usuário:
 * - "replace": remove todas as versões anteriores do mesmo `id` e guarda a nova
 * - "keep_both": mantém outras versões do mesmo `id` e guarda/atualiza `id@version`
 */
export function upsertMotionInLibrary(
  library: MotionLibraryEntry[],
  manifest: MotionManifest,
  html: string,
  resolution: "replace" | "keep_both" = "keep_both",
): MotionLibraryEntry[] {
  const key = motionKey(manifest.id, manifest.version);
  const entry: MotionLibraryEntry = {
    key,
    id: manifest.id,
    version: manifest.version,
    name: manifest.name,
    manifest,
    html,
    importedAt: new Date().toISOString(),
  };

  if (resolution === "replace") {
    return [...library.filter((it) => it.id !== manifest.id), entry];
  }
  const idx = library.findIndex((it) => it.key === key);
  if (idx >= 0) {
    const copy = [...library];
    copy[idx] = entry;
    return copy;
  }
  return [...library, entry];
}

/**
 * 5. PRESETS:
 * Aplica um preset salvo `{motionId, motionVersion, mode, params}` sobre o manifesto atual:
 * - Ignora params que não existem mais no manifesto
 * - Limita valores ao range [min, max] atual
 * - Avisa se a versão do motion no preset for diferente da versão atual
 */
export interface AppliedPresetResult {
  mode: string;
  params: Record<string, MotionParamValue>;
  ignoredParams: string[];
  clampedParams: string[];
  versionMismatch: boolean;
  warning: string | null;
}

export function applyMotionPreset(preset: MotionPreset, manifest: MotionManifest): AppliedPresetResult {
  const params = defaultParamsForManifest(manifest);
  const ignoredParams: string[] = [];
  const clampedParams: string[] = [];

  for (const [k, rawVal] of Object.entries(preset.params ?? {})) {
    const def = manifest.params[k];
    if (!def) {
      ignoredParams.push(k);
      continue;
    }
    if (def.type === "float" || def.type === "int") {
      const n = Number(rawVal);
      if (!Number.isFinite(n)) continue;
      const min = def.min ?? -Infinity;
      const max = def.max ?? Infinity;
      let clamped = Math.min(max, Math.max(min, n));
      if (def.type === "int") clamped = Math.round(clamped);
      if (clamped !== n) clampedParams.push(k);
      params[k] = clamped;
    } else if (def.type === "bool") {
      params[k] = Boolean(rawVal);
    } else if (def.type === "color") {
      if (typeof rawVal === "string" && HEX_COLOR_RE.test(rawVal.trim())) {
        params[k] = normalizeHexColor(rawVal.trim());
      }
    } else if (def.type === "select") {
      const s = String(rawVal);
      if (def.options?.some((o) => o.value === s)) {
        params[k] = s;
      } else {
        clampedParams.push(k);
      }
    } else if (def.type === "vec3") {
      if (Array.isArray(rawVal) && rawVal.length === 3 && rawVal.every((x) => Number.isFinite(Number(x)))) {
        const min = def.min ?? -Infinity;
        const max = def.max ?? Infinity;
        const orig = rawVal.map(Number) as Vec3;
        const next: Vec3 = [
          Math.min(max, Math.max(min, orig[0])),
          Math.min(max, Math.max(min, orig[1])),
          Math.min(max, Math.max(min, orig[2])),
        ];
        if (next[0] !== orig[0] || next[1] !== orig[1] || next[2] !== orig[2]) {
          clampedParams.push(k);
        }
        params[k] = next;
      }
    }
  }

  const validMode = manifest.modes.some((m) => m.id === preset.mode)
    ? preset.mode
    : (manifest.modes[0]?.id ?? "default");

  const versionMismatch = preset.motionVersion !== manifest.version;
  const warnings: string[] = [];
  if (versionMismatch) {
    warnings.push(
      `Versão diferente: o preset "${preset.name}" foi salvo para v${preset.motionVersion} (motion atual é v${manifest.version}).`,
    );
  }
  if (ignoredParams.length > 0) {
    warnings.push(`Parâmetros inexistentes ignorados: ${ignoredParams.join(", ")}.`);
  }
  if (clampedParams.length > 0) {
    warnings.push(`Valores limitados ao intervalo atual: ${clampedParams.join(", ")}.`);
  }

  return {
    mode: validMode,
    params,
    ignoredParams,
    clampedParams,
    versionMismatch,
    warning: warnings.length > 0 ? warnings.join(" ") : null,
  };
}

/**
 * 6. ÁUDIO CENTRAL:
 * Calcula bass (25–140 Hz), mid (250–2200 Hz), high (4–12 kHz), level e beat
 * (limiar adaptativo com cooldown), tudo normalizado em [0, 1].
 */
export interface BeatDetectorState {
  history: number[];
  lastBeatMs: number;
  beatPulse: number;
  beatCount: number;
}

export function createBeatDetectorState(): BeatDetectorState {
  return {
    history: [],
    lastBeatMs: -1000,
    beatPulse: 0,
    beatCount: 0,
  };
}

const clamp01 = (v: number): number => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));

export function bandAverage01(
  freqData: Uint8Array,
  sampleRate: number,
  fftSize: number,
  minHz: number,
  maxHz: number,
): number {
  if (!freqData.length || sampleRate <= 0 || fftSize <= 0) return 0;
  const binHz = sampleRate / fftSize;
  const startBin = Math.max(0, Math.floor(minHz / binHz));
  const endBin = Math.min(freqData.length - 1, Math.ceil(maxHz / binHz));
  if (endBin < startBin) return 0;
  let sum = 0;
  let count = 0;
  for (let i = startBin; i <= endBin; i++) {
    sum += freqData[i] / 255;
    count++;
  }
  return count > 0 ? clamp01(sum / count) : 0;
}

export function computeAudioFrame(
  freqData: Uint8Array,
  timeData: Uint8Array,
  sampleRate: number,
  fftSize: number,
  beatState: BeatDetectorState,
  nowMs: number,
  cooldownMs = 220,
): { frame: MotionAudioFrame; triggered: boolean } {
  const bass = bandAverage01(freqData, sampleRate, fftSize, 25, 140);
  const mid = bandAverage01(freqData, sampleRate, fftSize, 250, 2200);
  const high = bandAverage01(freqData, sampleRate, fftSize, 4000, 12000);

  let rmsSum = 0;
  if (timeData.length > 0) {
    for (let i = 0; i < timeData.length; i++) {
      const centered = (timeData[i] - 128) / 128;
      rmsSum += centered * centered;
    }
  }
  const rms = timeData.length > 0 ? Math.sqrt(rmsSum / timeData.length) : 0;
  const spectralLevel = (bass * 0.45 + mid * 0.35 + high * 0.2);
  const level = clamp01(Math.max(rms * 1.8, spectralLevel));

  // Limiar adaptativo sobre a energia de grave + nível com cooldown
  const energy = bass * 0.75 + level * 0.25;
  const hist = beatState.history;
  const mean = hist.length > 0 ? hist.reduce((a, b) => a + b, 0) / hist.length : 0;
  let variance = 0;
  if (hist.length > 1) {
    for (const v of hist) variance += (v - mean) * (v - mean);
    variance /= hist.length;
  }
  const std = Math.sqrt(variance);
  const adaptiveThreshold = Math.max(0.18, mean * 1.28 + std * 0.5);

  hist.push(energy);
  if (hist.length > 45) hist.shift();

  let triggered = false;
  if (energy > adaptiveThreshold && nowMs - beatState.lastBeatMs >= cooldownMs) {
    triggered = true;
    beatState.lastBeatMs = nowMs;
    beatState.beatPulse = 1;
    beatState.beatCount += 1;
  } else {
    beatState.beatPulse = clamp01(beatState.beatPulse * 0.82);
  }

  return {
    frame: {
      bass: Math.round(bass * 1000) / 1000,
      mid: Math.round(mid * 1000) / 1000,
      high: Math.round(high * 1000) / 1000,
      level: Math.round(level * 1000) / 1000,
      beat: triggered ? 1 : Math.round(beatState.beatPulse * 1000) / 1000,
    },
    triggered,
  };
}

/**
 * Motion Module v1 de exemplo autocontido para testes imediatos e demonstração.
 */
export const SAMPLE_MOTION_HTML = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<title>Neon Pulse Grid — Motion Module v1</title>
<script type="application/json" id="motion-manifest">
{
  "spec": "motion-module/1",
  "id": "neon-pulse-grid",
  "name": "Neon Pulse Grid",
  "version": "1.0.0",
  "author": "ProjMap Studio",
  "modes": [
    { "id": "cyber", "label": "Cyber Grid" },
    { "id": "minimal", "label": "Minimal Clean" },
    { "id": "storm", "label": "Beat Storm" }
  ],
  "triggers": [
    { "id": "reset", "label": "Resetar Fase" },
    { "id": "burst", "label": "Explosão de Pulso" },
    { "id": "clean_phase", "label": "Forçar Phase=clean" }
  ],
  "params": {
    "speed": {
      "type": "float",
      "label": "Velocidade",
      "group": "Movimento",
      "default": 1.2,
      "min": 0.0,
      "max": 5.0,
      "step": 0.1
    },
    "rings": {
      "type": "int",
      "label": "Anéis",
      "group": "Geometria",
      "default": 6,
      "min": 1,
      "max": 20,
      "step": 1
    },
    "mirror": {
      "type": "bool",
      "label": "Espelhar Simetria",
      "group": "Geometria",
      "default": true
    },
    "primaryColor": {
      "type": "color",
      "label": "Cor Principal",
      "group": "Cores",
      "default": "#7c5cff"
    },
    "palette": {
      "type": "select",
      "label": "Paleta",
      "group": "Cores",
      "default": "neon",
      "options": [
        { "value": "neon", "label": "Neon Violeta" },
        { "value": "solar", "label": "Solar Quente" },
        { "value": "cyber", "label": "Ciano Laser" }
      ]
    },
    "cameraOffset": {
      "type": "vec3",
      "label": "Deslocamento 3D",
      "group": "Câmera",
      "default": [0.0, 0.0, 1.0],
      "min": -2.0,
      "max": 2.0,
      "step": 0.05
    }
  }
}
</script>
<style>
  html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #05070d; color: #e8eef6; font-family: sans-serif; }
  canvas { width: 100%; height: 100%; display: block; }
  .hud { position: fixed; left: 8px; bottom: 8px; font-size: 11px; opacity: 0.78; pointer-events: none; background: rgba(0,0,0,0.55); padding: 4px 8px; border-radius: 6px; }
</style>
</head>
<body>
<canvas id="cv"></canvas>
<div class="hud" id="hud">Aguardando motion:init…</div>
<script>
(function() {
  const cv = document.getElementById("cv");
  const ctx = cv.getContext("2d");
  const hud = document.getElementById("hud");
  let state = {
    mode: "cyber",
    phase: "warmup",
    params: {
      speed: 1.2,
      rings: 6,
      mirror: true,
      primaryColor: "#7c5cff",
      palette: "neon",
      cameraOffset: [0, 0, 1]
    },
    audio: { bass: 0, mid: 0, high: 0, level: 0, beat: 0 },
    flash: 0,
    t: 0,
    destroyed: false
  };

  function send(type, payload) {
    if (window.parent) {
      window.parent.postMessage({ type: type, payload: payload || {} }, "*");
    }
  }

  window.addEventListener("message", function(ev) {
    const msg = ev.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "motion:init") {
      send("motion:ready", { id: "neon-pulse-grid", version: "1.0.0", phase: state.phase });
      send("motion:state", { phase: state.phase, mode: state.mode });
    } else if (msg.type === "motion:setParams") {
      Object.assign(state.params, msg.payload || {});
    } else if (msg.type === "motion:setMode") {
      state.mode = (msg.payload && msg.payload.mode) || state.mode;
      send("motion:state", { phase: state.phase, mode: state.mode });
    } else if (msg.type === "motion:trigger") {
      const tid = msg.payload && (msg.payload.id || msg.payload.name);
      if (tid === "reset") {
        state.t = 0;
        state.flash = 0.7;
        state.phase = "warmup";
      } else if (tid === "burst") {
        state.flash = 1.0;
        state.phase = "peak";
      } else if (tid === "clean_phase") {
        state.phase = "clean";
      }
      send("motion:event", { name: "trigger:" + tid, phase: state.phase });
      send("motion:state", { phase: state.phase, mode: state.mode });
    } else if (msg.type === "motion:audio") {
      state.audio = Object.assign(state.audio, msg.payload || {});
      if (state.audio.beat >= 0.9) {
        state.flash = Math.max(state.flash, 0.65);
      }
    } else if (msg.type === "motion:destroy") {
      state.destroyed = true;
    }
  });

  function draw() {
    if (state.destroyed) return;
    const w = (cv.width = cv.clientWidth || 320);
    const h = (cv.height = cv.clientHeight || 180);
    state.t += 0.016 * (Number(state.params.speed) || 1);
    state.flash *= 0.9;

    const a = state.audio;
    ctx.fillStyle = "#05070d";
    ctx.fillRect(0, 0, w, h);

    const off = Array.isArray(state.params.cameraOffset) ? state.params.cameraOffset : [0, 0, 1];
    const cx = w * 0.5 + Number(off[0] || 0) * 60;
    const cy = h * 0.5 + Number(off[1] || 0) * 40;
    const zoom = Math.max(0.25, Number(off[2] || 1));
    const rings = Math.max(1, Math.min(20, Math.round(Number(state.params.rings) || 6)));
    const baseCol = state.params.primaryColor || "#7c5cff";

    for (let i = 1; i <= rings; i++) {
      const r = (i / rings) * Math.min(w, h) * 0.42 * zoom * (1 + a.bass * 0.35 + state.flash * 0.2);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = i % 2 === 0 ? baseCol : (state.params.palette === "solar" ? "#fbbf24" : "#22d3ee");
      ctx.lineWidth = 1.5 + a.mid * 3;
      ctx.stroke();
    }

    hud.textContent = "mode=" + state.mode + " · phase=" + state.phase + " · bass=" + (a.bass || 0).toFixed(2) + " · beat=" + (a.beat || 0).toFixed(1);
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
</script>
</body>
</html>`;
