// Especificação "Motion Module v1" (motion-module/1):
// - Parse e validação estrita de manifesto HTML via DOMParser (sem executar scripts)
// - Validação estendida da convenção ProjMap DJ (seções 3 e 7 do motion_system_prompt.md)
// - Biblioteca versionada por (id, version) com histórico de geração e detecção de conflito
// - Presets nomeados com clamp de range, descarte de params obsoletos e aviso de versão
// - Motor de Áudio para DJ: AGC (~8s subida / ~2s descida), trim (-12..+12 dB), recalibrar,
//   sinais contínuos (bass, mid, high, level, energy), detectores de onset por fluxo espectral
//   positivo (kick 40-120Hz, snare 180-3500Hz, hat 6-14kHz), estimador de BPM (70-180) com
//   grid travado após ~8 batidas, beatPhase/barPhase, downbeat, tap tempo, batida manual e
//   compensação de latência (Antecipação 0-150 ms).
// - Teste de fumaça em iframe oculto 480x480 e malha de validação/reparo automático com Claude.

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
  tags?: string[];
  defaultMode?: string;
  params: Record<string, MotionParamDef>;
  modes: MotionModeDef[];
  triggers: MotionTriggerDef[];
  events?: string[];
  phases?: string[];
}

export interface MotionValidationError {
  field: string;
  message: string;
}

export type MotionParseResult =
  | { ok: true; manifest: MotionManifest; html: string }
  | { ok: false; errors: MotionValidationError[] };

export interface MotionGenerationRecord {
  timestamp: string;
  kind: "new" | "edit" | "repair";
  prompt: string;
  imagesCount: number;
  notes: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens: number;
    cache_read_input_tokens: number;
    estimated_cost_usd: number;
  };
}

export interface MotionLibraryEntry {
  key: string; // `${id}@${version}`
  id: string;
  version: string;
  name: string;
  manifest: MotionManifest;
  html: string;
  importedAt: string;
  notes?: string;
  history?: MotionGenerationRecord[];
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

export type ReactToMacro = "mix" | "bass" | "high" | "beat" | "custom";

export const REACT_TO_OPTIONS: { value: ReactToMacro; label: string; shortcut: string }[] = [
  { value: "mix", label: "Mix", shortcut: "1" },
  { value: "bass", label: "Graves", shortcut: "2" },
  { value: "high", label: "Agudos", shortcut: "3" },
  { value: "beat", label: "Batidas", shortcut: "4" },
  { value: "custom", label: "Personalizado", shortcut: "5" },
];

export interface MotionAudioFrame {
  // Contínuos (0..1)
  bass: number;     // 25–140 Hz
  mid: number;      // 250–2200 Hz
  high: number;     // 4–12 kHz
  level: number;    // volume geral ponderado
  energy: number;   // média móvel de ~4 s do level
  // Eventos (impulso 0..1 no frame da detecção, 0 nos demais)
  kick: number;     // onset 40–120 Hz (cooldown 0.18 s)
  snare: number;    // onset 180–3500 Hz (cooldown 0.15 s)
  hat: number;      // onset 6–14 kHz (cooldown 0.07 s)
  beat: number;     // pulso principal do tempo (grid quando travado, senão kick)
  downbeat: number; // primeiro tempo do compasso (a cada 4 beats)
  // Tempo
  bpm: number;       // 0 se desconhecido (faixa 70–180)
  beatPhase: number; // rampa 0->1 dentro de cada batida
  barPhase: number;  // rampa 0->1 dentro de cada compasso de 4 tempos
}

export const EMPTY_AUDIO_FRAME: MotionAudioFrame = {
  bass: 0,
  mid: 0,
  high: 0,
  level: 0,
  energy: 0,
  kick: 0,
  snare: 0,
  hat: 0,
  beat: 0,
  downbeat: 0,
  bpm: 0,
  beatPhase: 0,
  barPhase: 0,
};

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

function parseVec3Value(v: unknown): Vec3 | null {
  if (Array.isArray(v) && v.length === 3 && v.every(isFiniteNum)) {
    return [v[0], v[1], v[2]];
  }
  if (v && typeof v === "object" && !Array.isArray(v)) {
    const o = v as Record<string, unknown>;
    if (isFiniteNum(o.x) && isFiniteNum(o.y) && isFiniteNum(o.z)) {
      return [o.x, o.y, o.z];
    }
  }
  return null;
}

function parseScalarBound(v: unknown): number | null {
  if (isFiniteNum(v)) return v;
  const vec = parseVec3Value(v);
  if (vec) return vec[0];
  return null;
}

/**
 * 1. IMPORTAÇÃO:
 * Lê o manifesto com DOMParser sem executar o arquivo HTML e valida:
 * - spec === "motion-module/1"
 * - id, name e version presentes
 * - cada param com tipo válido (float, int, bool, color, select, vec3) e default dentro de min/max.
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
      message: 'Campo "params" deve ser um objeto ou array de definições de parâmetros.',
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
        const min = parseScalarBound(p.min);
        const max = parseScalarBound(p.max);
        let rangeOk = true;
        if (min === null) {
          errors.push({ field: `${prefix}.min`, message: `Campo "${prefix}.min" deve ser numérico.` });
          rangeOk = false;
        }
        if (max === null) {
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
        const vec = parseVec3Value(p.default);
        if (!vec) {
          errors.push({
            field: `${prefix}.default`,
            message: `Campo "${prefix}.default" deve ser [x, y, z] ou {x, y, z} numérico.`,
          });
        } else if (rangeOk) {
          const [x, y, z] = vec;
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
    tags: Array.isArray(obj.tags) ? obj.tags.map(String) : undefined,
    defaultMode: typeof obj.defaultMode === "string" ? obj.defaultMode : undefined,
    params: paramsOut,
    modes: modes.length > 0 ? modes : [{ id: "default", label: "Padrão" }],
    triggers,
    events: Array.isArray(obj.events) ? obj.events.map(String) : undefined,
    phases: Array.isArray(obj.phases) ? obj.phases.map(String) : undefined,
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

/**
 * Extrai os alvos de reação (<alvo>) definidos por `rx_<alvo>_src` no manifesto (Seção 7.2).
 */
export function extractReactionTargets(manifest: MotionManifest): string[] {
  const targets: string[] = [];
  for (const key of Object.keys(manifest.params)) {
    const m = /^rx_([a-zA-Z0-9_]+)_src$/.exec(key);
    if (m) targets.push(m[1]);
  }
  return targets;
}

/**
 * C.4 Etapa 1: Validação estática estrita para motions gerados pelo Claude
 * (checa todos os params obrigatórios das seções 3 e 7.2 do motion_system_prompt.md).
 */
export function validateGeneratedMotionStrict(html: string): MotionParseResult {
  const base = parseAndValidateMotionHtml(html);
  if (!base.ok) return base;

  const { manifest } = base;
  const p = manifest.params;
  const errors: MotionValidationError[] = [];

  // Seção 3: Parâmetros obrigatórios
  const bg = p.background;
  if (!bg || bg.type !== "select") {
    errors.push({ field: "params.background", message: "Parâmetro obrigatório 'background' (select) ausente." });
  } else {
    const vals = new Set((bg.options ?? []).map((o) => o.value));
    if (!vals.has("black") || !vals.has("transparent")) {
      errors.push({
        field: "params.background.options",
        message: "'background' deve incluir as opções 'black' e 'transparent'.",
      });
    }
  }

  const framing = p.framing;
  if (!framing || framing.type !== "select") {
    errors.push({ field: "params.framing", message: "Parâmetro obrigatório 'framing' (select) ausente." });
  } else {
    const vals = new Set((framing.options ?? []).map((o) => o.value));
    if (!vals.has("element")) {
      errors.push({
        field: "params.framing.options",
        message: "'framing' deve incluir a opção 'element'.",
      });
    }
  }

  const reqTypes: [string, MotionParamType][] = [
    ["seed", "int"],
    ["scale", "float"],
    ["offsetX", "float"],
    ["offsetY", "float"],
    ["exposure", "float"],
    ["interactive", "bool"],
    ["reactAmount", "float"],
    ["sensitivity", "float"],
    ["beatCooldown", "float"],
    ["tempoSync", "bool"],
  ];

  for (const [k, expectedType] of reqTypes) {
    if (!p[k] || p[k].type !== expectedType) {
      errors.push({
        field: `params.${k}`,
        message: `Parâmetro obrigatório '${k}' (${expectedType}) ausente ou com tipo incorreto.`,
      });
    }
  }

  const reactTo = p.reactTo;
  if (!reactTo || reactTo.type !== "select") {
    errors.push({ field: "params.reactTo", message: "Parâmetro obrigatório 'reactTo' (select) ausente." });
  } else {
    const vals = new Set((reactTo.options ?? []).map((o) => o.value));
    for (const reqOpt of ["mix", "bass", "high", "beat", "custom"]) {
      if (!vals.has(reqOpt)) {
        errors.push({
          field: "params.reactTo.options",
          message: `'reactTo' deve conter as 5 opções (faltando '${reqOpt}').`,
        });
      }
    }
  }

  // Pelo menos 2 alvos com o trio rx_<alvo>_src, rx_<alvo>_amt, rx_<alvo>_smooth
  const targets = extractReactionTargets(manifest);
  const completeTargets = targets.filter(
    (t) =>
      p[`rx_${t}_src`]?.type === "select" &&
      p[`rx_${t}_amt`]?.type === "float" &&
      p[`rx_${t}_smooth`]?.type === "float",
  );
  if (completeTargets.length < 2) {
    errors.push({
      field: "params.rx_*",
      message: `O manifesto deve declarar pelo menos 2 alvos de reação completos (rx_<alvo>_src, rx_<alvo>_amt, rx_<alvo>_smooth); encontrados: ${completeTargets.length}.`,
    });
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }
  return base;
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
  extra?: { notes?: string; generationRecord?: MotionGenerationRecord },
): MotionLibraryEntry[] {
  const key = motionKey(manifest.id, manifest.version);
  const prevSameId = library.filter((it) => it.id === manifest.id);
  const prevHistory = prevSameId.flatMap((it) => it.history ?? []);
  const history = extra?.generationRecord ? [...prevHistory, extra.generationRecord] : prevHistory;

  const entry: MotionLibraryEntry = {
    key,
    id: manifest.id,
    version: manifest.version,
    name: manifest.name,
    manifest,
    html,
    importedAt: new Date().toISOString(),
    notes: extra?.notes ?? prevSameId[prevSameId.length - 1]?.notes,
    history: history.length > 0 ? history : undefined,
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
 * Aplica um preset salvo `{motionId, motionVersion, mode, params}` sobre o manifesto atual.
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
      const orig = parseVec3Value(rawVal);
      if (orig) {
        const min = def.min ?? -Infinity;
        const max = def.max ?? Infinity;
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

// ============================================================================
// A. MOTOR DE ÁUDIO PARA DJ
// ============================================================================

export interface OnsetBandState {
  prevEnergy: number;
  fluxHistory: Array<{ tMs: number; flux: number }>;
  lastTriggerMs: number;
  armed: boolean;
}

export interface BeatDetectorState {
  // Compatibilidade legada
  history: number[];
  lastBeatMs: number;
  beatPulse: number;
  beatCount: number;

  // AGC (~8s para subir ganho, ~2s para descer ganho)
  agcRef: number;
  agcInitialized: boolean;
  agcGain: number;
  gainTrimDb: number; // -12 a +12 dB

  // Energy (~4s média móvel do level)
  energySamples: Array<{ tMs: number; level: number }>;

  // Detectores de onset por banda (fluxo espectral positivo + rearme + cooldown)
  kickOnset: OnsetBandState;  // 40–120 Hz, cooldown 180 ms
  snareOnset: OnsetBandState; // 180–3500 Hz, cooldown 150 ms
  hatOnset: OnsetBandState;   // 6000–14000 Hz, cooldown 70 ms

  // Estimador de BPM (70–180 BPM) e Grid de Fase
  kickTimestamps: number[];
  bpmHistogram: Float64Array; // 221 bins: 70.0 a 180.0 em passos de 0.5 BPM
  bpm: number;
  bpmLocked: boolean;
  ConsistentKickIntervals: number;
  gridOriginMs: number;
  lastGridBeatIndex: number;
  realignNextBeat: boolean;

  // Tap tempo e batida manual
  tapTimestamps: number[];
  manualBeatPending: boolean;

  // Compensação de latência (Antecipação 0..150 ms)
  anticipationMs: number;
  lastFrameMs: number;
}

function makeOnsetState(): OnsetBandState {
  return {
    prevEnergy: 0,
    fluxHistory: [],
    lastTriggerMs: -10000,
    armed: true,
  };
}

export function createBeatDetectorState(): BeatDetectorState {
  return {
    history: [],
    lastBeatMs: -10000,
    beatPulse: 0,
    beatCount: 0,
    agcRef: 0.5,
    agcInitialized: false,
    agcGain: 1.0,
    gainTrimDb: 0,
    energySamples: [],
    kickOnset: makeOnsetState(),
    snareOnset: makeOnsetState(),
    hatOnset: makeOnsetState(),
    kickTimestamps: [],
    bpmHistogram: new Float64Array(221),
    bpm: 0,
    bpmLocked: false,
    ConsistentKickIntervals: 0,
    gridOriginMs: 0,
    lastGridBeatIndex: -1,
    realignNextBeat: false,
    tapTimestamps: [],
    manualBeatPending: false,
    anticipationMs: 0,
    lastFrameMs: -1,
  };
}

/** Botão "Recalibrar": zera o histórico do AGC. */
export function recalibrateAgc(state: BeatDetectorState): void {
  state.agcRef = 0.5;
  state.agcInitialized = false;
  state.agcGain = 1.0;
  state.energySamples = [];
}

/** Botão "Realinhar o compasso" no próximo beat. */
export function realignDownbeatOnNextBeat(state: BeatDetectorState): void {
  state.realignNextBeat = true;
}

/** Tap tempo (tecla T e botão): sobrescreve o BPM estimado e trava o grid. */
export function registerTapTempo(state: BeatDetectorState, nowMs: number): number {
  state.tapTimestamps = state.tapTimestamps.filter((t) => nowMs - t < 4000);
  state.tapTimestamps.push(nowMs);
  if (state.tapTimestamps.length >= 2) {
    const intervals: number[] = [];
    for (let i = 1; i < state.tapTimestamps.length; i++) {
      intervals.push(state.tapTimestamps[i] - state.tapTimestamps[i - 1]);
    }
    const avgIoi = intervals.reduce((a, b) => a + b, 0) / intervals.length;
    const tapBpm = 60000 / Math.max(1, avgIoi);
    if (tapBpm >= 70 && tapBpm <= 180) {
      state.bpm = Math.round(tapBpm * 10) / 10;
      state.bpmLocked = true;
      state.gridOriginMs = nowMs;
      state.lastGridBeatIndex = 0;
    }
  }
  return state.bpm;
}

/** Batida manual (tecla B e botão): dispara beat + kick com força 1 no próximo ciclo. */
export function triggerManualBeat(state: BeatDetectorState): void {
  state.manualBeatPending = true;
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

function detectBandOnset(
  onset: OnsetBandState,
  bandEnergy: number,
  nowMs: number,
  cooldownMs: number,
  kStd = 1.4,
  minFlux = 0.04,
): number {
  const flux = Math.max(0, bandEnergy - onset.prevEnergy);
  onset.prevEnergy = bandEnergy;

  // Janela de ~1 s para média e desvio padrão do fluxo espectral positivo
  while (onset.fluxHistory.length > 0 && nowMs - onset.fluxHistory[0].tMs > 1000) {
    onset.fluxHistory.shift();
  }

  let mean = 0;
  let std = 0;
  if (onset.fluxHistory.length > 0) {
    for (const item of onset.fluxHistory) mean += item.flux;
    mean /= onset.fluxHistory.length;
    let variance = 0;
    for (const item of onset.fluxHistory) {
      const d = item.flux - mean;
      variance += d * d;
    }
    std = Math.sqrt(variance / onset.fluxHistory.length);
  }

  // Rearme quando o fluxo cai abaixo ou igual à média
  if (flux <= mean + 1e-5) {
    onset.armed = true;
  }

  const threshold = Math.max(minFlux, mean + kStd * std);
  let strength = 0;
  if (onset.armed && flux > threshold && nowMs - onset.lastTriggerMs >= cooldownMs) {
    onset.armed = false;
    onset.lastTriggerMs = nowMs;
    strength = clamp01(Math.min(1, (flux - mean) / Math.max(0.12, 0.5 - mean)));
    if (strength < 0.35) strength = 0.75;
  }

  onset.fluxHistory.push({ tMs: nowMs, flux });
  return Math.round(strength * 1000) / 1000;
}

function updateBpmFromKick(state: BeatDetectorState, kickTimeMs: number): void {
  const kicks = state.kickTimestamps;
  kicks.push(kickTimeMs);
  while (kicks.length > 24) kicks.shift();

  if (kicks.length < 2) return;
  const ioiMs = kickTimeMs - kicks[kicks.length - 2];
  if (ioiMs <= 0) return;

  // Normaliza o intervalo para a faixa 70–180 BPM (333.3 ms a 857.1 ms)
  let candBpm = 60000 / ioiMs;
  while (candBpm < 70 && candBpm > 17.5) candBpm *= 2;
  while (candBpm > 180 && candBpm < 720) candBpm /= 2;
  if (candBpm < 70 || candBpm > 180) return;

  // Decai o histograma e adiciona voto gaussiano em torno de candBpm
  const hist = state.bpmHistogram;
  for (let i = 0; i < hist.length; i++) {
    hist[i] *= 0.92;
  }
  const centerIdx = Math.round((candBpm - 70) * 2);
  for (let offset = -3; offset <= 3; offset++) {
    const idx = centerIdx + offset;
    if (idx >= 0 && idx < hist.length) {
      hist[idx] += Math.exp(-(offset * offset) / 2);
    }
  }

  // Encontra o pico do histograma
  let bestIdx = 0;
  let bestWeight = 0;
  for (let i = 0; i < hist.length; i++) {
    if (hist[i] > bestWeight) {
      bestWeight = hist[i];
      bestIdx = i;
    }
  }
  const histBpm = 70 + bestIdx * 0.5;
  const expectedIoi = 60000 / histBpm;

  // Conta quantos intervalos recentes são consistentes (~8 batidas = 7 intervalos)
  const consistentIois: number[] = [];
  for (let i = kicks.length - 1; i >= 1; i--) {
    const dt = kicks[i] - kicks[i - 1];
    if (Math.abs(dt - expectedIoi) / expectedIoi <= 0.07) {
      consistentIois.push(dt);
    } else {
      break;
    }
  }

  state.ConsistentKickIntervals = consistentIois.length;
  if (consistentIois.length >= 2) {
    // Média exata dos intervalos consistentes para precisão < 0.2 BPM
    const meanIoi = consistentIois.reduce((a, b) => a + b, 0) / consistentIois.length;
    state.bpm = Math.round((60000 / meanIoi) * 100) / 100;
  } else {
    state.bpm = Math.round(histBpm * 10) / 10;
  }

  // Trava o grid de fase quando estável por ~8 batidas (>= 7 intervalos consistentes)
  if (consistentIois.length >= 7) {
    if (!state.bpmLocked) {
      state.bpmLocked = true;
      state.gridOriginMs = kickTimeMs;
      state.lastGridBeatIndex = 0;
    }
  }
}

export function computeAudioFrame(
  freqData: Uint8Array,
  timeData: Uint8Array,
  sampleRate: number,
  fftSize: number,
  beatState: BeatDetectorState,
  nowMs: number,
  _cooldownMs = 220,
): { frame: MotionAudioFrame; triggered: boolean } {
  const dtS =
    beatState.lastFrameMs >= 0 && nowMs > beatState.lastFrameMs
      ? Math.min(0.5, (nowMs - beatState.lastFrameMs) / 1000)
      : 1 / 60;
  beatState.lastFrameMs = nowMs;

  // Bandas cruas (0..1)
  const rawBass = bandAverage01(freqData, sampleRate, fftSize, 25, 140);
  const rawMid = bandAverage01(freqData, sampleRate, fftSize, 250, 2200);
  const rawHigh = bandAverage01(freqData, sampleRate, fftSize, 4000, 12000);

  let rmsSum = 0;
  if (timeData.length > 0) {
    for (let i = 0; i < timeData.length; i++) {
      const centered = (timeData[i] - 128) / 128;
      rmsSum += centered * centered;
    }
  }
  const rawRms = timeData.length > 0 ? Math.sqrt(rmsSum / timeData.length) : 0;
  const rawSpectral = rawBass * 0.45 + rawMid * 0.35 + rawHigh * 0.2;
  const rawPeak = Math.max(rawBass, rawMid, rawHigh, rawRms * 1.4, rawSpectral);

  // 1. Controle Automático de Ganho (AGC)
  // Constante de tempo ~8 s para subir o ganho (quando o som cai) e ~2 s para descer o ganho (quando o som sobe)
  const TARGET_REF = 0.65;
  if (rawPeak > 1e-4) {
    if (!beatState.agcInitialized) {
      beatState.agcRef = rawPeak;
      beatState.agcInitialized = true;
    } else {
      // Se rawPeak > agcRef, o som ficou mais alto -> ganho precisa DESCER (~2 s)
      // Se rawPeak < agcRef, o som ficou mais baixo -> ganho precisa SUBIR (~8 s)
      const tau = rawPeak > beatState.agcRef ? 2.0 : 8.0;
      const alpha = 1 - Math.exp(-dtS / tau);
      beatState.agcRef += alpha * (rawPeak - beatState.agcRef);
    }
  }
  const autoGain = Math.min(20.0, Math.max(0.2, TARGET_REF / Math.max(beatState.agcRef, 1e-4)));
  beatState.agcGain = autoGain;

  const trimDb = Math.min(12, Math.max(-12, beatState.gainTrimDb || 0));
  const trimLinear = Math.pow(10, trimDb / 20);
  const totalGain = autoGain * trimLinear;

  const bass = clamp01(rawBass * totalGain);
  const mid = clamp01(rawMid * totalGain);
  const high = clamp01(rawHigh * totalGain);
  const level = clamp01(Math.max(rawRms * 1.4 * totalGain, bass * 0.45 + mid * 0.35 + high * 0.2));

  // Energy: média móvel de ~4 s do level
  beatState.energySamples.push({ tMs: nowMs, level });
  while (beatState.energySamples.length > 0 && nowMs - beatState.energySamples[0].tMs > 4000) {
    beatState.energySamples.shift();
  }
  const energy =
    beatState.energySamples.length > 0
      ? clamp01(beatState.energySamples.reduce((acc, s) => acc + s.level, 0) / beatState.energySamples.length)
      : level;

  // 2. Detectores de onset por banda (kick 40-120Hz, snare 180-3500Hz, hat 6-14kHz)
  const kickBand = clamp01(bandAverage01(freqData, sampleRate, fftSize, 40, 120) * totalGain);
  const snareBand = clamp01(bandAverage01(freqData, sampleRate, fftSize, 180, 3500) * totalGain);
  const hatBand = clamp01(bandAverage01(freqData, sampleRate, fftSize, 6000, 14000) * totalGain);

  let kick = detectBandOnset(beatState.kickOnset, kickBand, nowMs, 180, 1.35, 0.05);
  const snare = detectBandOnset(beatState.snareOnset, snareBand, nowMs, 150, 1.4, 0.05);
  const hat = detectBandOnset(beatState.hatOnset, hatBand, nowMs, 70, 1.4, 0.04);

  if (beatState.manualBeatPending) {
    beatState.manualBeatPending = false;
    kick = 1;
  }

  if (kick > 0) {
    updateBpmFromKick(beatState, nowMs);
  }

  // 3. Tempo, Grid de Fase e Compensação de Latência (Antecipação 0..150 ms)
  const anticipation = Math.min(150, Math.max(0, beatState.anticipationMs || 0));
  const effectiveNowMs = nowMs + anticipation;

  let beat = 0;
  let downbeat = 0;
  let beatPhase = 0;
  let barPhase = 0;

  if (beatState.bpmLocked && beatState.bpm > 0) {
    const beatPeriodMs = 60000 / beatState.bpm;
    const elapsedFromOrigin = effectiveNowMs - beatState.gridOriginMs;
    const exactBeats = elapsedFromOrigin / beatPeriodMs;
    const currentBeatIdx = Math.floor(exactBeats);
    beatPhase = clamp01(exactBeats - currentBeatIdx);

    if (currentBeatIdx > beatState.lastGridBeatIndex) {
      beatState.lastGridBeatIndex = currentBeatIdx;
      beat = 1;
      beatState.beatCount += 1;
      beatState.lastBeatMs = nowMs;
      if (beatState.realignNextBeat) {
        beatState.realignNextBeat = false;
        beatState.gridOriginMs = effectiveNowMs;
        beatState.lastGridBeatIndex = 0;
        downbeat = 1;
      } else if (beatState.beatCount % 4 === 1) {
        downbeat = 1;
      }
    }
    const barBeats = ((exactBeats % 4) + 4) % 4;
    barPhase = clamp01(barBeats / 4);
  } else {
    // Sem grid travado: beat = kick
    if (kick > 0) {
      beat = kick;
      beatState.beatCount += 1;
      beatState.lastBeatMs = nowMs;
      if (beatState.realignNextBeat) {
        beatState.realignNextBeat = false;
        downbeat = 1;
      } else if (beatState.beatCount % 4 === 1) {
        downbeat = 1;
      }
    }
  }

  const triggered = beat > 0;
  const round3 = (n: number) => Math.round(clamp01(n) * 1000) / 1000;

  return {
    frame: {
      bass: round3(bass),
      mid: round3(mid),
      high: round3(high),
      level: round3(level),
      energy: round3(energy),
      kick: round3(kick),
      snare: round3(snare),
      hat: round3(hat),
      beat: round3(beat),
      downbeat: round3(downbeat),
      bpm: beatState.bpm,
      beatPhase: round3(beatPhase),
      barPhase: round3(barPhase),
    },
    triggered,
  };
}

// ============================================================================
// C.2 & C.4 EXTRAÇÃO E TESTE DE FUMAÇA EM EXECUÇÃO (IFRAME OCULTO 480x480)
// ============================================================================

export interface ExtractedClaudeMotion {
  ok: boolean;
  html: string;
  layerPreset: Record<string, unknown>;
  notes: string;
  errors: string[];
}

export function extractClaudeMotionResponse(rawText: string): ExtractedClaudeMotion {
  const errors: string[] = [];
  const htmlMatch = /<motion_html>\s*([\s\S]*?)\s*<\/motion_html>/.exec(rawText || "");
  const presetMatch = /<layer_preset>\s*([\s\S]*?)\s*<\/layer_preset>/.exec(rawText || "");
  const notesMatch = /<notes>\s*([\s\S]*?)\s*<\/notes>/.exec(rawText || "");

  if (!htmlMatch || !htmlMatch[1].trim()) {
    errors.push("Marcação <motion_html>...</motion_html> ausente ou vazia.");
  }
  if (!presetMatch || !presetMatch[1].trim()) {
    errors.push("Marcação <layer_preset>...</layer_preset> ausente ou vazia.");
  }
  if (!notesMatch || !notesMatch[1].trim()) {
    errors.push("Marcação <notes>...</notes> ausente ou vazia.");
  }

  let layerPreset: Record<string, unknown> = {};
  if (presetMatch && presetMatch[1].trim()) {
    try {
      const parsed = JSON.parse(presetMatch[1].trim());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        errors.push("<layer_preset> deve conter um objeto JSON válido.");
      } else {
        layerPreset = parsed as Record<string, unknown>;
      }
    } catch (e) {
      errors.push(`JSON inválido em <layer_preset>: ${e instanceof Error ? e.message : "erro de sintaxe"}`);
    }
  }

  return {
    ok: errors.length === 0,
    html: htmlMatch ? htmlMatch[1].trim() : "",
    layerPreset,
    notes: notesMatch ? notesMatch[1].trim() : "",
    errors,
  };
}

export interface SmokeTestOptions {
  readyTimeoutMs?: number;
  audioDurationMs?: number;
  stepMs?: number;
}

export interface SmokeTestResult {
  ok: boolean;
  errors: string[];
  beatEventsReceived: number;
}

/**
 * C.4 Etapa 2: Teste de fumaça em execução num iframe oculto de 480x480:
 * - Espera motion:ready por até 8 s
 * - Envia 4 s de motion:audio sintético (kick/beat a cada 0.47s, hat a cada 0.12s, bass/mid/high oscilando, energy subindo)
 * - Aplica layer_preset via motion:setParams e alterna reactTo entre as 5 opções
 * - Coleta todo motion:error e exige pelo menos um motion:event "beat" de volta.
 */
export async function runMotionSmokeTest(
  html: string,
  layerPreset?: Record<string, unknown>,
  options?: SmokeTestOptions,
): Promise<SmokeTestResult> {
  const readyTimeoutMs = options?.readyTimeoutMs ?? 8000;
  const audioDurationMs = options?.audioDurationMs ?? 4000;
  const stepMs = options?.stepMs ?? 50;

  const errors: string[] = [];
  let beatEventsReceived = 0;
  let readyReceived = false;

  const blob = new Blob([html], { type: "text/html" });
  const blobUrl = URL.createObjectURL(blob);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-scripts");
  iframe.style.position = "fixed";
  iframe.style.left = "-9999px";
  iframe.style.top = "-9999px";
  iframe.style.width = "480px";
  iframe.style.height = "480px";
  iframe.style.opacity = "0";
  iframe.style.pointerEvents = "none";

  return new Promise<SmokeTestResult>((resolve) => {
    let finished = false;
    let readyResolve: (() => void) | null = null;

    const cleanup = () => {
      window.removeEventListener("message", onMessage);
      try {
        iframe.contentWindow?.postMessage({ type: "motion:destroy", payload: {} }, "*");
      } catch {
        /* ignore */
      }
      if (iframe.parentNode) iframe.remove();
      URL.revokeObjectURL(blobUrl);
    };

    const finish = (ok: boolean, extraErrors: string[] = []) => {
      if (finished) return;
      finished = true;
      cleanup();
      const allErrors = [...errors, ...extraErrors];
      resolve({
        ok: ok && allErrors.length === 0,
        errors: allErrors,
        beatEventsReceived,
      });
    };

    const onMessage = (ev: MessageEvent) => {
      if (!iframe.contentWindow || ev.source !== iframe.contentWindow) return;
      const data = ev.data;
      if (!data || typeof data !== "object") return;
      const { type, payload } = data as { type?: string; payload?: Record<string, unknown> };
      if (type === "motion:ready") {
        readyReceived = true;
        if (readyResolve) readyResolve();
      } else if (type === "motion:error") {
        const msg = String(payload?.message ?? JSON.stringify(payload ?? "Erro desconhecido no motion"));
        errors.push(`motion:error: ${msg}`);
      } else if (type === "motion:event") {
        if (payload?.name === "beat") {
          beatEventsReceived += 1;
        }
      }
    };

    window.addEventListener("message", onMessage);

    iframe.onload = async () => {
      const win = iframe.contentWindow;
      if (!win) {
        finish(false, ["Iframe do teste de fumaça não expôs contentWindow."]);
        return;
      }

      win.postMessage({ type: "motion:init", payload: { embed: true, audioSource: "external" } }, "*");

      await new Promise<void>((r) => {
        if (readyReceived) {
          r();
          return;
        }
        readyResolve = r;
        window.setTimeout(() => r(), readyTimeoutMs);
      });

      if (!readyReceived) {
        finish(false, [`Timeout: motion:ready não recebido em ${readyTimeoutMs} ms no teste de fumaça.`]);
        return;
      }

      if (errors.length > 0) {
        finish(false);
        return;
      }

      // Aplica layer_preset via motion:setParams
      const presetParams =
        layerPreset && typeof layerPreset.params === "object" && layerPreset.params !== null
          ? (layerPreset.params as Record<string, unknown>)
          : {};
      win.postMessage({ type: "motion:setParams", payload: presetParams }, "*");

      const reactModes: ReactToMacro[] = ["mix", "bass", "high", "beat", "custom"];
      const steps = Math.max(1, Math.floor(audioDurationMs / stepMs));

      for (let i = 0; i < steps; i++) {
        if (errors.length > 0) break;
        const tS = (i * stepMs) / 1000;
        const isKick = Math.abs((tS % 0.47) - 0) < stepMs / 1000;
        const isHat = Math.abs((tS % 0.12) - 0) < stepMs / 1000;
        const reactIdx = Math.min(reactModes.length - 1, Math.floor((i / steps) * reactModes.length));

        if (i % Math.max(1, Math.floor(steps / 5)) === 0) {
          win.postMessage({ type: "motion:setParams", payload: { reactTo: reactModes[reactIdx] } }, "*");
        }

        const synthFrame: MotionAudioFrame = {
          bass: Math.round((0.5 + 0.45 * Math.sin(tS * 4)) * 100) / 100,
          mid: Math.round((0.4 + 0.35 * Math.cos(tS * 3)) * 100) / 100,
          high: Math.round((0.35 + 0.4 * Math.sin(tS * 7)) * 100) / 100,
          level: Math.round((0.4 + 0.5 * (tS / (audioDurationMs / 1000))) * 100) / 100,
          energy: Math.round(Math.min(1, 0.2 + 0.75 * (tS / (audioDurationMs / 1000))) * 100) / 100,
          kick: isKick ? 1 : 0,
          snare: isKick && i % 2 === 1 ? 0.85 : 0,
          hat: isHat ? 0.9 : 0,
          beat: isKick ? 1 : 0,
          downbeat: isKick && i % 4 === 0 ? 1 : 0,
          bpm: 128,
          beatPhase: (tS % 0.47) / 0.47,
          barPhase: (tS % 1.88) / 1.88,
        };
        win.postMessage({ type: "motion:audio", payload: synthFrame }, "*");
        await new Promise((r) => window.setTimeout(r, stepMs));
      }

      if (beatEventsReceived < 1) {
        errors.push('O motion não enviou nenhum motion:event {name: "beat"} durante os 4 s de áudio sintético.');
      }

      finish(errors.length === 0);
    };

    document.body.appendChild(iframe);
    iframe.src = blobUrl;
  });
}

/**
 * Motion Module v1 de exemplo autocontido, seguindo integralmente o motion_system_prompt.md
 * (parâmetros obrigatórios da seção 3 + matriz de reação da seção 7.2 + envio de motion:event beat).
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
  "description": "Anéis neon reativos a kick e agudos para projeção mapeada em shows de DJ",
  "author": "ProjMap Studio",
  "tags": ["neon", "grid", "dj", "camada"],
  "defaultMode": "cyber",
  "audio": { "internal": ["demo", "file", "mic"], "external": true },
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
  "events": ["beat", "phase"],
  "phases": ["warmup", "peak", "clean"],
  "params": {
    "background": {
      "type": "select",
      "label": "Fundo",
      "group": "Camada",
      "default": "scene",
      "options": [
        { "value": "scene", "label": "Cena original" },
        { "value": "black", "label": "Preto (#000)" },
        { "value": "transparent", "label": "Transparente (Camada)" }
      ]
    },
    "framing": {
      "type": "select",
      "label": "Enquadramento",
      "group": "Camada",
      "default": "scene",
      "options": [
        { "value": "scene", "label": "Cena completa" },
        { "value": "element", "label": "Elemento recortado" }
      ]
    },
    "seed": {
      "type": "int",
      "label": "Semente (Seed)",
      "group": "Camada",
      "default": 42,
      "min": 0,
      "max": 999,
      "step": 1
    },
    "scale": {
      "type": "float",
      "label": "Escala",
      "group": "Camada",
      "default": 1.0,
      "min": 0.2,
      "max": 3.0,
      "step": 0.05
    },
    "offsetX": {
      "type": "float",
      "label": "Posição X",
      "group": "Camada",
      "default": 0.0,
      "min": -1.0,
      "max": 1.0,
      "step": 0.01
    },
    "offsetY": {
      "type": "float",
      "label": "Posição Y",
      "group": "Camada",
      "default": 0.0,
      "min": -1.0,
      "max": 1.0,
      "step": 0.01
    },
    "exposure": {
      "type": "float",
      "label": "Exposição",
      "group": "Camada",
      "default": 1.0,
      "min": 0.2,
      "max": 2.5,
      "step": 0.05
    },
    "interactive": {
      "type": "bool",
      "label": "Clique gera batida",
      "group": "Camada",
      "default": true
    },
    "reactTo": {
      "type": "select",
      "label": "Reagir a",
      "group": "Reação ao áudio",
      "default": "mix",
      "options": [
        { "value": "mix", "label": "Mix sugerido" },
        { "value": "bass", "label": "Graves" },
        { "value": "high", "label": "Agudos" },
        { "value": "beat", "label": "Batidas" },
        { "value": "custom", "label": "Personalizado" }
      ]
    },
    "reactAmount": {
      "type": "float",
      "label": "Intensidade Geral",
      "group": "Reação ao áudio",
      "default": 1.0,
      "min": 0.0,
      "max": 2.0,
      "step": 0.05
    },
    "sensitivity": {
      "type": "float",
      "label": "Sensibilidade",
      "group": "Reação ao áudio",
      "default": 1.0,
      "min": 0.5,
      "max": 2.0,
      "step": 0.05
    },
    "beatCooldown": {
      "type": "float",
      "label": "Cooldown de Gatilho (s)",
      "group": "Reação ao áudio",
      "default": 0.22,
      "min": 0.1,
      "max": 0.6,
      "step": 0.01
    },
    "tempoSync": {
      "type": "bool",
      "label": "Sincronizar ao BPM",
      "group": "Reação ao áudio",
      "default": false
    },
    "rx_deform_src": {
      "type": "select",
      "label": "Deformação · Fonte",
      "group": "Reação ao áudio",
      "default": "bass",
      "options": [
        { "value": "bass", "label": "Graves (bass)" },
        { "value": "mid", "label": "Médios (mid)" },
        { "value": "high", "label": "Agudos (high)" },
        { "value": "level", "label": "Volume (level)" },
        { "value": "energy", "label": "Energia (energy)" },
        { "value": "kick", "label": "Kick" },
        { "value": "snare", "label": "Snare" },
        { "value": "hat", "label": "Hat" },
        { "value": "beat", "label": "Beat" },
        { "value": "downbeat", "label": "Downbeat" },
        { "value": "off", "label": "Desligado" }
      ]
    },
    "rx_deform_amt": {
      "type": "float",
      "label": "Deformação · Intensidade",
      "group": "Reação ao áudio",
      "default": 1.0,
      "min": 0.0,
      "max": 2.0,
      "step": 0.05
    },
    "rx_deform_smooth": {
      "type": "float",
      "label": "Deformação · Suavização (s)",
      "group": "Reação ao áudio",
      "default": 0.15,
      "min": 0.02,
      "max": 1.0,
      "step": 0.02
    },
    "rx_pulse_src": {
      "type": "select",
      "label": "Ondulação · Fonte",
      "group": "Reação ao áudio",
      "default": "kick",
      "options": [
        { "value": "bass", "label": "Graves (bass)" },
        { "value": "mid", "label": "Médios (mid)" },
        { "value": "high", "label": "Agudos (high)" },
        { "value": "level", "label": "Volume (level)" },
        { "value": "energy", "label": "Energia (energy)" },
        { "value": "kick", "label": "Kick" },
        { "value": "snare", "label": "Snare" },
        { "value": "hat", "label": "Hat" },
        { "value": "beat", "label": "Beat" },
        { "value": "downbeat", "label": "Downbeat" },
        { "value": "off", "label": "Desligado" }
      ]
    },
    "rx_pulse_amt": {
      "type": "float",
      "label": "Ondulação · Intensidade",
      "group": "Reação ao áudio",
      "default": 1.0,
      "min": 0.0,
      "max": 2.0,
      "step": 0.05
    },
    "rx_pulse_smooth": {
      "type": "float",
      "label": "Ondulação · Decaimento (s)",
      "group": "Reação ao áudio",
      "default": 0.25,
      "min": 0.02,
      "max": 1.0,
      "step": 0.02
    },
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
  :root { color-scheme: normal; }
  html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; color: #e8eef6; font-family: sans-serif; }
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
      background: "scene",
      framing: "scene",
      seed: 42,
      scale: 1.0,
      offsetX: 0.0,
      offsetY: 0.0,
      exposure: 1.0,
      interactive: true,
      reactTo: "mix",
      reactAmount: 1.0,
      sensitivity: 1.0,
      beatCooldown: 0.22,
      tempoSync: false,
      rx_deform_src: "bass",
      rx_deform_amt: 1.0,
      rx_deform_smooth: 0.15,
      rx_pulse_src: "kick",
      rx_pulse_amt: 1.0,
      rx_pulse_smooth: 0.25,
      speed: 1.2,
      rings: 6,
      mirror: true,
      primaryColor: "#7c5cff",
      palette: "neon",
      cameraOffset: [0, 0, 1]
    },
    audio: { bass: 0, mid: 0, high: 0, level: 0, energy: 0, kick: 0, snare: 0, hat: 0, beat: 0, downbeat: 0, bpm: 0, beatPhase: 0, barPhase: 0 },
    flash: 0,
    t: 0,
    destroyed: false
  };

  function send(type, payload) {
    if (window.parent) {
      window.parent.postMessage({ type: type, payload: payload || {} }, "*");
    }
  }

  window.addEventListener("error", function(e) {
    send("motion:error", { message: String(e.message || e.error || "window.onerror") });
  });

  window.addEventListener("message", function(ev) {
    const msg = ev.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "motion:init") {
      if (msg.payload && msg.payload.embed) {
        hud.style.display = "none";
      }
      send("motion:ready", { id: "neon-pulse-grid", version: "1.0.0", phase: state.phase });
      send("motion:state", { phase: state.phase, mode: state.mode, params: state.params });
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
      const pulseHit = state.audio.kick || state.audio.beat || 0;
      if (pulseHit >= 0.5) {
        state.flash = Math.max(state.flash, pulseHit);
        send("motion:event", { name: "beat", data: { strength: pulseHit } });
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
    ctx.clearRect(0, 0, w, h);
    if (state.params.background !== "transparent") {
      ctx.fillStyle = state.params.background === "black" ? "#000000" : "#05070d";
      ctx.fillRect(0, 0, w, h);
    }

    const off = Array.isArray(state.params.cameraOffset) ? state.params.cameraOffset : [0, 0, 1];
    const cx = w * (0.5 + Number(state.params.offsetX || 0) * 0.4) + Number(off[0] || 0) * 40;
    const cy = h * (0.5 + Number(state.params.offsetY || 0) * 0.4) + Number(off[1] || 0) * 30;
    const zoom = Math.max(0.2, Number(state.params.scale || 1) * Number(off[2] || 1));
    const rings = Math.max(1, Math.min(20, Math.round(Number(state.params.rings) || 6)));
    const baseCol = state.params.primaryColor || "#7c5cff";

    for (let i = 1; i <= rings; i++) {
      const r = (i / rings) * Math.min(w, h) * 0.42 * zoom * (1 + a.bass * 0.35 + state.flash * 0.2);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = i % 2 === 0 ? baseCol : (state.params.palette === "solar" ? "#fbbf24" : "#22d3ee");
      ctx.lineWidth = (1.5 + a.mid * 3) * Number(state.params.exposure || 1);
      ctx.stroke();
    }

    hud.textContent = "mode=" + state.mode + " · phase=" + state.phase + " · bass=" + (a.bass || 0).toFixed(2) + " · bpm=" + (a.bpm || 0);
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
</script>
</body>
</html>`;
