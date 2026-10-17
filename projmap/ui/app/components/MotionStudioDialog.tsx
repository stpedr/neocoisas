"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyMotionPreset,
  computeAudioFrame,
  createBeatDetectorState,
  defaultParamsForManifest,
  findExistingById,
  groupManifestParams,
  motionKey,
  parseAndValidateMotionHtml,
  SAMPLE_MOTION_HTML,
  upsertMotionInLibrary,
  type MotionAudioFrame,
  type MotionLibraryEntry,
  type MotionManifest,
  type MotionParamDef,
  type MotionParamValue,
  type MotionPreset,
  type MotionRule,
  type MotionValidationError,
  type Vec3,
} from "../lib/motionModule";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";

const LIB_STORAGE_KEY = "projmap.motions.library.v1";
const PRESETS_STORAGE_KEY = "projmap.motions.presets.v1";
const RULES_STORAGE_KEY = "projmap.motions.rules.v1";
const READY_TIMEOUT_MS = 5000;

export interface ActiveMotionSlot {
  slotId: string;
  motionKey: string;
}

interface PendingConflict {
  manifest: MotionManifest;
  html: string;
  existingVersions: string[];
}

export interface MotionHandle {
  postAudio: (frame: MotionAudioFrame) => void;
  postTrigger: (triggerId: string) => void;
}

function loadStoredJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveStoredJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore storage quota */
  }
}

interface MotionSlotRunnerProps {
  slotId: string;
  entry: MotionLibraryEntry;
  presets: MotionPreset[];
  beatActive: boolean;
  onSavePreset: (preset: MotionPreset) => void;
  onDeletePreset: (id: string) => void;
  onPhaseChange: (slotId: string, phase: string) => void;
  onRemoveSlot: (slotId: string) => void;
  registerHandle: (slotId: string, handle: MotionHandle | null) => void;
}

export function MotionSlotRunner({
  slotId,
  entry,
  presets,
  beatActive,
  onSavePreset,
  onDeletePreset,
  onPhaseChange,
  onRemoveSlot,
  registerHandle,
}: MotionSlotRunnerProps) {
  const { manifest, html } = entry;
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const contentWinRef = useRef<Window | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const readyTimerRef = useRef<number | null>(null);
  const destroyedRef = useRef<boolean>(false);

  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<string>(manifest.modes[0]?.id ?? "default");
  const [params, setParams] = useState<Record<string, MotionParamValue>>(() => defaultParamsForManifest(manifest));
  const [phase, setPhase] = useState<string>("idle");
  const [lastEvent, setLastEvent] = useState<string>("—");
  const [presetName, setPresetName] = useState<string>("");
  const [presetWarning, setPresetWarning] = useState<string | null>(null);

  const postToMotion = useCallback((type: string, payload: unknown = {}) => {
    const win = iframeRef.current?.contentWindow ?? contentWinRef.current;
    if (win) {
      contentWinRef.current = win;
      win.postMessage({ type, payload }, "*");
    }
  }, []);

  const cleanupMotionInstance = useCallback(() => {
    if (destroyedRef.current) return;
    destroyedRef.current = true;
    if (readyTimerRef.current !== null) {
      window.clearTimeout(readyTimerRef.current);
      readyTimerRef.current = null;
    }
    const iframeEl = iframeRef.current;
    const win = iframeEl?.contentWindow ?? contentWinRef.current;
    if (win) {
      try {
        win.postMessage({ type: "motion:destroy", payload: {} }, "*");
      } catch {
        /* ignore */
      }
      contentWinRef.current = null;
    }
    if (iframeEl && iframeEl.parentNode) {
      iframeEl.remove();
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
  }, []);

  // Expõe handle para o áudio central e triggers automáticos de beat
  useEffect(() => {
    registerHandle(slotId, {
      postAudio: (frame) => postToMotion("motion:audio", frame),
      postTrigger: (triggerId) => postToMotion("motion:trigger", { id: triggerId, name: triggerId }),
    });
    return () => registerHandle(slotId, null);
  }, [slotId, postToMotion, registerHandle]);

  // 3. EXECUÇÃO + 8. CICLO DE VIDA:
  // Cria blob URL, gerencia timeout de 5s para motion:ready e no cleanup envia
  // motion:destroy, remove o iframe e revoga o blob URL.
  useEffect(() => {
    destroyedRef.current = false;
    setStatus("loading");
    setErrorMsg(null);
    setMode(manifest.modes[0]?.id ?? "default");
    setParams(defaultParamsForManifest(manifest));
    setPhase("idle");
    setLastEvent("—");
    setPresetWarning(null);

    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    blobUrlRef.current = url;
    setBlobUrl(url);

    return () => {
      cleanupMotionInstance();
    };
  }, [entry.key, html, manifest, cleanupMotionInstance]);

  // Escuta mensagens exclusivamente deste iframe (event.source === iframe.contentWindow)
  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      const iframeWin = iframeRef.current?.contentWindow;
      if (!iframeWin || ev.source !== iframeWin) return;
      const data = ev.data;
      if (!data || typeof data !== "object") return;
      const { type, payload } = data as { type?: string; payload?: Record<string, unknown> };

      if (type === "motion:ready") {
        if (readyTimerRef.current !== null) {
          window.clearTimeout(readyTimerRef.current);
          readyTimerRef.current = null;
        }
        setStatus("ready");
        setErrorMsg(null);
        if (payload && typeof payload.phase === "string") {
          setPhase(payload.phase);
          onPhaseChange(slotId, payload.phase);
        }
      } else if (type === "motion:state") {
        if (payload && typeof payload.phase === "string") {
          setPhase(payload.phase);
          onPhaseChange(slotId, payload.phase);
        }
      } else if (type === "motion:event") {
        const evName = String(payload?.name ?? payload?.id ?? JSON.stringify(payload ?? {}));
        setLastEvent(evName);
        if (payload && typeof payload.phase === "string") {
          setPhase(payload.phase);
          onPhaseChange(slotId, payload.phase);
        }
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [slotId, onPhaseChange]);

  const handleIframeLoad = () => {
    if (readyTimerRef.current !== null) {
      window.clearTimeout(readyTimerRef.current);
    }
    postToMotion("motion:init", { embed: true, audioSource: "external" });
    readyTimerRef.current = window.setTimeout(() => {
      setStatus((cur) => {
        if (cur !== "ready") {
          setErrorMsg("Erro: motion:ready não recebido em até 5 s.");
          return "error";
        }
        return cur;
      });
    }, READY_TIMEOUT_MS);
  };

  // 4. PAINEL AUTOMÁTICO: cada alteração envia motion:setParams na hora
  const updateParam = (key: string, value: MotionParamValue) => {
    setParams((prev) => {
      const next = { ...prev, [key]: value };
      postToMotion("motion:setParams", next);
      return next;
    });
  };

  const changeMode = (nextMode: string) => {
    setMode(nextMode);
    postToMotion("motion:setMode", { mode: nextMode });
    postToMotion("motion:setParams", { ...params, mode: nextMode });
  };

  const fireTrigger = (triggerId: string) => {
    postToMotion("motion:trigger", { id: triggerId, name: triggerId });
  };

  // 5. PRESETS
  const motionPresets = useMemo(
    () => presets.filter((p) => p.motionId === manifest.id),
    [presets, manifest.id],
  );

  const handleSavePreset = () => {
    const name = presetName.trim() || `${manifest.name} (${mode})`;
    const preset: MotionPreset = {
      id: `preset-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      motionId: manifest.id,
      motionVersion: manifest.version,
      mode,
      params: { ...params },
      createdAt: new Date().toISOString(),
    };
    onSavePreset(preset);
    setPresetName("");
  };

  const handleLoadPreset = (preset: MotionPreset) => {
    const applied = applyMotionPreset(preset, manifest);
    setMode(applied.mode);
    setParams(applied.params);
    setPresetWarning(applied.warning);
    postToMotion("motion:setMode", { mode: applied.mode });
    postToMotion("motion:setParams", applied.params);
  };

  const groups = useMemo(() => groupManifestParams(manifest), [manifest]);

  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-border bg-secondary/40 p-3"
      data-testid={`motion-slot-${slotId}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
        <div className="flex items-center gap-2">
          <strong className="text-sm text-foreground">{manifest.name}</strong>
          <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
            {manifest.id}@{manifest.version}
          </span>
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
              status === "ready"
                ? "bg-emerald-500/20 text-emerald-300"
                : status === "error"
                  ? "bg-red-500/20 text-red-300"
                  : "bg-amber-500/20 text-amber-300"
            }`}
            data-testid={`motion-status-${slotId}`}
          >
            {status === "ready" ? "Pronto (motion:ready)" : status === "error" ? "Erro (Timeout 5s)" : "Iniciando…"}
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span title="Fase atual reportada via motion:state">
            Fase: <b data-testid={`motion-phase-${slotId}`}>{phase}</b>
          </span>
          <span>
            Evento: <code className="text-xs">{lastEvent}</code>
          </span>
          <span
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-semibold ${
              beatActive ? "bg-purple-500 text-white" : "bg-secondary text-muted-foreground"
            }`}
            data-testid={`motion-beat-indicator-${slotId}`}
          >
            ● Beat
          </span>
          <button
            type="button"
            className="btn btn-small btn-danger"
            onClick={() => {
              cleanupMotionInstance();
              onRemoveSlot(slotId);
            }}
            title="Enviar motion:destroy, remover iframe e revogar blob URL"
          >
            Remover Motion
          </button>
        </div>
      </div>

      {errorMsg && (
        <div role="alert" className="rounded border border-red-500/50 bg-red-950/40 p-2 text-xs text-red-200">
          {errorMsg}
        </div>
      )}

      {/* Iframe isolado em sandbox="allow-scripts" (SEM allow-same-origin) via blob URL */}
      <div className="relative aspect-video w-full overflow-hidden rounded border border-border bg-black">
        {blobUrl && (
          <iframe
            ref={iframeRef}
            src={blobUrl}
            sandbox="allow-scripts"
            title={`Motion ${manifest.name} (${manifest.id}@${manifest.version})`}
            className="h-full w-full border-0"
            onLoad={handleIframeLoad}
            data-testid={`motion-iframe-${slotId}`}
          />
        )}
      </div>

      {/* Modos e Triggers */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          Modo
          <select
            aria-label={`Modo de ${manifest.name}`}
            value={mode}
            onChange={(e) => changeMode(e.target.value)}
            className="rounded border border-border bg-secondary px-2 py-1 text-xs text-foreground"
          >
            {manifest.modes.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>

        {manifest.triggers.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Triggers:</span>
            {manifest.triggers.map((tr) => (
              <button
                key={tr.id}
                type="button"
                className="btn btn-small"
                onClick={() => fireTrigger(tr.id)}
              >
                ⚡ {tr.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Painel Automático agrupado por "group" */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {Object.entries(groups).map(([groupName, groupDefs]) => (
          <fieldset key={groupName} className="flex flex-col gap-2 rounded border border-border p-2.5">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">{groupName}</legend>
            {groupDefs.map((def) => (
              <ParamControl
                key={def.key}
                def={def}
                value={params[def.key] ?? def.default}
                onChange={(val) => updateParam(def.key, val)}
              />
            ))}
          </fieldset>
        ))}
      </div>

      {/* Presets do Motion */}
      <div className="flex flex-col gap-2 border-t border-border pt-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground">Presets:</span>
          <input
            type="text"
            placeholder="Nome do preset…"
            aria-label="Nome do preset"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            className="rounded border border-border bg-secondary px-2 py-1 text-xs text-foreground"
          />
          <button type="button" className="btn btn-small" onClick={handleSavePreset}>
            Salvar Preset
          </button>
          {motionPresets.map((p) => (
            <span key={p.id} className="inline-flex items-center gap-1 rounded border border-border bg-secondary px-2 py-0.5 text-xs">
              <button
                type="button"
                className="font-medium text-foreground hover:underline"
                onClick={() => handleLoadPreset(p)}
                title={`Carregar preset ${p.name} (v${p.motionVersion})`}
              >
                {p.name} <span className="text-muted-foreground">(v{p.motionVersion})</span>
              </button>
              <button
                type="button"
                aria-label={`Excluir preset ${p.name}`}
                className="text-muted-foreground hover:text-red-400"
                onClick={() => onDeletePreset(p.id)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        {presetWarning && (
          <div
            role="status"
            data-testid={`preset-warning-${slotId}`}
            className="rounded border border-amber-500/50 bg-amber-950/40 p-2 text-xs text-amber-200"
          >
            ⚠ {presetWarning}
          </div>
        )}
      </div>
    </div>
  );
}

function ParamControl({
  def,
  value,
  onChange,
}: {
  def: MotionParamDef;
  value: MotionParamValue;
  onChange: (v: MotionParamValue) => void;
}) {
  if (def.type === "float" || def.type === "int") {
    const num = typeof value === "number" ? value : Number(def.default);
    const min = def.min ?? 0;
    const max = def.max ?? 1;
    const step = def.step ?? (def.type === "int" ? 1 : 0.01);
    const handleNum = (raw: string) => {
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) return;
      const clamped = Math.min(max, Math.max(min, def.type === "int" ? Math.round(parsed) : parsed));
      onChange(clamped);
    };
    return (
      <div className="flex flex-col gap-1 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span>{def.label}</span>
          <input
            type="number"
            aria-label={`${def.label} valor`}
            min={min}
            max={max}
            step={step}
            value={num}
            onChange={(e) => handleNum(e.target.value)}
            className="w-20 rounded border border-border bg-secondary px-1.5 py-0.5 text-right text-xs text-foreground"
          />
        </div>
        <input
          type="range"
          aria-label={def.label}
          min={min}
          max={max}
          step={step}
          value={num}
          onChange={(e) => handleNum(e.target.value)}
        />
      </div>
    );
  }

  if (def.type === "bool") {
    const checked = Boolean(value);
    return (
      <label className="flex items-center justify-between gap-2 text-xs">
        <span>{def.label}</span>
        <input
          type="checkbox"
          aria-label={def.label}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
      </label>
    );
  }

  if (def.type === "color") {
    const col = typeof value === "string" ? value : String(def.default);
    return (
      <label className="flex items-center justify-between gap-2 text-xs">
        <span>{def.label}</span>
        <input
          type="color"
          aria-label={def.label}
          value={col}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 w-14 rounded border border-border bg-secondary p-0.5"
        />
      </label>
    );
  }

  if (def.type === "select") {
    const sel = String(value);
    return (
      <label className="flex items-center justify-between gap-2 text-xs">
        <span>{def.label}</span>
        <select
          aria-label={def.label}
          value={sel}
          onChange={(e) => onChange(e.target.value)}
          className="rounded border border-border bg-secondary px-2 py-1 text-xs text-foreground"
        >
          {(def.options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  // vec3 -> três sliders + inputs numéricos (X, Y, Z)
  const vec: Vec3 = Array.isArray(value) && value.length === 3 ? (value as Vec3) : (def.default as Vec3);
  const min = def.min ?? -1;
  const max = def.max ?? 1;
  const step = def.step ?? 0.01;
  const axes = ["X", "Y", "Z"] as const;

  const setAxis = (idx: 0 | 1 | 2, raw: string) => {
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    const clamped = Math.min(max, Math.max(min, n));
    const next: Vec3 = [vec[0], vec[1], vec[2]];
    next[idx] = clamped;
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-1 text-xs">
      <span className="font-medium">{def.label} (vec3)</span>
      {axes.map((axis, idx) => {
        const i = idx as 0 | 1 | 2;
        return (
          <div key={axis} className="flex items-center gap-2">
            <span className="w-4 text-muted-foreground">{axis}</span>
            <input
              type="range"
              aria-label={`${def.label} ${axis}`}
              min={min}
              max={max}
              step={step}
              value={vec[i]}
              onChange={(e) => setAxis(i, e.target.value)}
              className="flex-1"
            />
            <input
              type="number"
              aria-label={`${def.label} ${axis} valor`}
              min={min}
              max={max}
              step={step}
              value={vec[i]}
              onChange={(e) => setAxis(i, e.target.value)}
              className="w-16 rounded border border-border bg-secondary px-1 py-0.5 text-right text-xs"
            />
          </div>
        );
      })}
    </div>
  );
}

interface MotionStudioDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function MotionStudioDialog({ open, onClose }: MotionStudioDialogProps) {
  const [library, setLibrary] = useState<MotionLibraryEntry[]>([]);
  const [presets, setPresets] = useState<MotionPreset[]>([]);
  const [rules, setRules] = useState<MotionRule[]>([]);
  const [slots, setSlots] = useState<ActiveMotionSlot[]>([]);
  const [validationErrors, setValidationErrors] = useState<MotionValidationError[]>([]);
  const [pendingConflict, setPendingConflict] = useState<PendingConflict | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // 6. ÁUDIO CENTRAL (um único AudioContext + AnalyserNode no host)
  const [audioSourceKind, setAudioSourceKind] = useState<"none" | "file" | "mic" | "line">("none");
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [lineDeviceId, setLineDeviceId] = useState<string>("");
  const [audioFrame, setAudioFrame] = useState<MotionAudioFrame>({ bass: 0, mid: 0, high: 0, level: 0, beat: 0 });
  const [beatCount, setBeatCount] = useState<number>(0);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const fileObjectUrlRef = useRef<string | null>(null);
  const beatStateRef = useRef(createBeatDetectorState());
  const handlesRef = useRef<Map<string, MotionHandle>>(new Map());
  const rulesRef = useRef<MotionRule[]>([]);
  rulesRef.current = rules;

  // Formulário de nova regra
  const [ruleKind, setRuleKind] = useState<"phase_switch" | "beat_trigger">("phase_switch");
  const [rulePhase, setRulePhase] = useState<string>("clean");
  const [ruleTargetMotion, setRuleTargetMotion] = useState<string>("");
  const [ruleEveryBeats, setRuleEveryBeats] = useState<number>(4);
  const [ruleTriggerId, setRuleTriggerId] = useState<string>("reset");

  useEffect(() => {
    const savedLib = loadStoredJson<MotionLibraryEntry[]>(LIB_STORAGE_KEY, []);
    const savedPresets = loadStoredJson<MotionPreset[]>(PRESETS_STORAGE_KEY, []);
    const savedRules = loadStoredJson<MotionRule[]>(RULES_STORAGE_KEY, []);
    setLibrary(savedLib);
    setPresets(savedPresets);
    setRules(savedRules);
  }, []);

  const persistLibrary = (next: MotionLibraryEntry[]) => {
    setLibrary(next);
    saveStoredJson(LIB_STORAGE_KEY, next);
  };

  const persistPresets = (next: MotionPreset[]) => {
    setPresets(next);
    saveStoredJson(PRESETS_STORAGE_KEY, next);
  };

  const persistRules = (next: MotionRule[]) => {
    setRules(next);
    saveStoredJson(RULES_STORAGE_KEY, next);
  };

  const registerHandle = useCallback((slotId: string, handle: MotionHandle | null) => {
    if (handle) handlesRef.current.set(slotId, handle);
    else handlesRef.current.delete(slotId);
  }, []);

  // 1. IMPORTAÇÃO + 2. BIBLIOTECA
  const importHtmlContent = useCallback(
    (htmlText: string) => {
      setValidationErrors([]);
      setPendingConflict(null);
      const res = parseAndValidateMotionHtml(htmlText);
      if (!res.ok) {
        setValidationErrors(res.errors);
        return;
      }
      const existing = findExistingById(library, res.manifest.id);
      if (existing.length > 0) {
        setPendingConflict({
          manifest: res.manifest,
          html: res.html,
          existingVersions: existing.map((e) => e.version),
        });
        return;
      }
      const nextLib = upsertMotionInLibrary(library, res.manifest, res.html, "keep_both");
      persistLibrary(nextLib);
      const key = motionKey(res.manifest.id, res.manifest.version);
      if (slots.length === 0) {
        setSlots([{ slotId: `slot-${Date.now()}`, motionKey: key }]);
      }
    },
    [library, slots.length],
  );

  const resolveConflict = (resolution: "replace" | "keep_both") => {
    if (!pendingConflict) return;
    const { manifest, html } = pendingConflict;
    const nextLib = upsertMotionInLibrary(library, manifest, html, resolution);
    persistLibrary(nextLib);
    const newKey = motionKey(manifest.id, manifest.version);
    if (resolution === "replace") {
      setSlots((cur) =>
        cur.map((s) => (s.motionKey.startsWith(`${manifest.id}@`) ? { ...s, motionKey: newKey } : s)),
      );
    }
    setPendingConflict(null);
  };

  const handleFileInput = async (file: File) => {
    const text = await file.text();
    importHtmlContent(text);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      await handleFileInput(file);
    }
  };

  const launchMotionSlot = (key: string) => {
    setSlots((cur) => [...cur, { slotId: `slot-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, motionKey: key }]);
  };

  const removeSlot = useCallback((slotId: string) => {
    setSlots((cur) => cur.filter((s) => s.slotId !== slotId));
  }, []);

  // 7. EVENTOS E ESTADO: aplica regra "quando phase = X, trocar para o motion Y"
  const handlePhaseChange = useCallback(
    (slotId: string, newPhase: string) => {
      for (const r of rulesRef.current) {
        if (r.enabled && r.kind === "phase_switch" && r.whenPhase === newPhase) {
          setSlots((cur) =>
            cur.map((s) => (s.slotId === slotId && s.motionKey !== r.targetMotionKey ? { ...s, motionKey: r.targetMotionKey } : s)),
          );
          break;
        }
      }
    },
    [],
  );

  // Dispara um beat manual ou automático (e executa regras "trigger X a cada N beats")
  const dispatchBeat = useCallback((frame: MotionAudioFrame, triggered: boolean, totalBeats: number) => {
    handlesRef.current.forEach((h) => h.postAudio(frame));
    if (triggered && totalBeats > 0) {
      for (const r of rulesRef.current) {
        if (r.enabled && r.kind === "beat_trigger" && r.everyNBeats > 0 && totalBeats % r.everyNBeats === 0) {
          handlesRef.current.forEach((h) => h.postTrigger(r.triggerId));
        }
      }
    }
  }, []);

  // 6. ÁUDIO CENTRAL: loop de análise FFT + envio sincronizado para todos os motions ativos
  const stopAudioSource = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current.src = "";
      audioElRef.current = null;
    }
    if (fileObjectUrlRef.current) {
      URL.revokeObjectURL(fileObjectUrlRef.current);
      fileObjectUrlRef.current = null;
    }
  }, []);

  const ensureAudioAnalyser = (): { ctx: AudioContext; analyser: AnalyserNode } => {
    if (!audioCtxRef.current) {
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioCtxRef.current = new Ctx();
    }
    if (!analyserRef.current) {
      const an = audioCtxRef.current.createAnalyser();
      an.fftSize = 2048;
      an.smoothingTimeConstant = 0.75;
      analyserRef.current = an;
    }
    if (audioCtxRef.current.state === "suspended") {
      void audioCtxRef.current.resume();
    }
    return { ctx: audioCtxRef.current, analyser: analyserRef.current };
  };

  const startMicOrLine = async (kind: "mic" | "line", deviceId?: string) => {
    stopAudioSource();
    setAudioSourceKind(kind);
    try {
      const constraints: MediaStreamConstraints =
        kind === "line"
          ? {
              audio: {
                ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
              },
            }
          : { audio: true };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      mediaStreamRef.current = stream;
      const { ctx, analyser } = ensureAudioAnalyser();
      const src = ctx.createMediaStreamSource(stream);
      src.connect(analyser);
      const devs = await navigator.mediaDevices.enumerateDevices();
      setAudioDevices(devs.filter((d) => d.kind === "audioinput"));
    } catch {
      setAudioSourceKind("none");
    }
  };

  const startAudioFile = (file: File) => {
    stopAudioSource();
    setAudioSourceKind("file");
    const url = URL.createObjectURL(file);
    fileObjectUrlRef.current = url;
    const audio = new Audio(url);
    audio.loop = true;
    audioElRef.current = audio;
    const { ctx, analyser } = ensureAudioAnalyser();
    const src = ctx.createMediaElementSource(audio);
    src.connect(analyser);
    analyser.connect(ctx.destination);
    void audio.play().catch(() => {});
  };

  useEffect(() => {
    if (!open) return;
    let raf = 0;
    const freqBuf = new Uint8Array(1024);
    const timeBuf = new Uint8Array(2048);

    const tick = (nowMs: number) => {
      const an = analyserRef.current;
      const ctx = audioCtxRef.current;
      if (an && ctx && audioSourceKind !== "none") {
        an.getByteFrequencyData(freqBuf);
        an.getByteTimeDomainData(timeBuf);
        const { frame, triggered } = computeAudioFrame(
          freqBuf,
          timeBuf,
          ctx.sampleRate || 44100,
          an.fftSize || 2048,
          beatStateRef.current,
          nowMs,
        );
        setAudioFrame(frame);
        if (triggered) {
          setBeatCount(beatStateRef.current.beatCount);
        }
        dispatchBeat(frame, triggered, beatStateRef.current.beatCount);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [open, audioSourceKind, dispatchBeat]);

  useEffect(() => {
    return () => stopAudioSource();
  }, [stopAudioSource]);

  const simulatePulseBeat = () => {
    beatStateRef.current.beatCount += 1;
    const total = beatStateRef.current.beatCount;
    setBeatCount(total);
    const frame: MotionAudioFrame = { bass: 0.92, mid: 0.65, high: 0.45, level: 0.85, beat: 1 };
    setAudioFrame(frame);
    dispatchBeat(frame, true, total);
  };

  const addRule = () => {
    const id = `rule-${Date.now()}`;
    if (ruleKind === "phase_switch") {
      const target = ruleTargetMotion || library[0]?.key || "";
      if (!target || !rulePhase.trim()) return;
      persistRules([
        ...rules,
        { id, enabled: true, kind: "phase_switch", whenPhase: rulePhase.trim(), targetMotionKey: target },
      ]);
    } else {
      if (!ruleTriggerId.trim() || ruleEveryBeats < 1) return;
      persistRules([
        ...rules,
        { id, enabled: true, kind: "beat_trigger", everyNBeats: Math.max(1, Math.round(ruleEveryBeats)), triggerId: ruleTriggerId.trim() },
      ]);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent aria-label="Motion Module v1 Studio" className="max-h-[92vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>🎬 Motion Module v1 — Importador, Biblioteca e Host Sincronizado</DialogTitle>
          <button type="button" className="btn btn-small" onClick={onClose}>
            Fechar
          </button>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {/* 1. IMPORTAÇÃO (Arrastar e soltar ou seletor de arquivo .html) */}
          <section
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            data-testid="motion-dropzone"
            className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border-2 border-dashed p-3 transition ${
              dragOver ? "border-primary bg-primary/10" : "border-border-strong bg-secondary/40"
            }`}
          >
            <div className="flex flex-col gap-0.5">
              <strong className="text-sm">1. Importar Motion Module v1 (.html)</strong>
              <span className="text-xs text-muted-foreground">
                Arraste e solte um arquivo <code>.html</code> aqui ou selecione do computador. O manifesto é validado via{" "}
                <code>DOMParser</code> sem executar scripts.
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="btn btn-accent btn-small cursor-pointer">
                Selecionar .html
                <input
                  type="file"
                  accept=".html,text/html"
                  hidden
                  data-testid="motion-file-input"
                  onChange={(e) => e.target.files?.[0] && void handleFileInput(e.target.files[0])}
                />
              </label>
              <button
                type="button"
                className="btn btn-small"
                onClick={() => importHtmlContent(SAMPLE_MOTION_HTML)}
                title="Importa o motion de demonstração Neon Pulse Grid v1.0.0"
              >
                + Carregar Exemplo v1
              </button>
            </div>
          </section>

          {/* Erros detalhados por campo na validação do manifesto */}
          {validationErrors.length > 0 && (
            <div
              role="alert"
              data-testid="motion-validation-errors"
              className="rounded-lg border border-red-500/60 bg-red-950/50 p-3 text-xs text-red-200"
            >
              <strong className="block mb-1 text-red-300">Falha na validação do manifesto Motion Module v1:</strong>
              <ul className="list-disc pl-5 space-y-0.5">
                {validationErrors.map((err, i) => (
                  <li key={i}>
                    <code className="font-bold text-red-100">{err.field}</code>: {err.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 2. BIBLIOTECA: pergunta se substitui ou mantém as duas versões quando o id já existe */}
          {pendingConflict && (
            <div
              role="alertdialog"
              aria-label="Conflito de versão na biblioteca"
              data-testid="motion-conflict-prompt"
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/60 bg-amber-950/50 p-3 text-xs text-amber-100"
            >
              <div>
                <strong>O motion &ldquo;{pendingConflict.manifest.id}&rdquo; já existe na biblioteca</strong> (versão existente:{" "}
                <code>{pendingConflict.existingVersions.join(", ")}</code>; nova versão:{" "}
                <code>{pendingConflict.manifest.version}</code>). Deseja substituir ou manter as duas versões?
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn btn-accent btn-small"
                  onClick={() => resolveConflict("replace")}
                >
                  Substituir
                </button>
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() => resolveConflict("keep_both")}
                >
                  Manter as duas versões
                </button>
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() => setPendingConflict(null)}
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}

          {/* Lista da Biblioteca */}
          <section className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/30 p-3">
            <div className="flex items-center justify-between">
              <strong className="text-xs uppercase tracking-wider text-muted-foreground">
                2. Biblioteca de Motions ({library.length})
              </strong>
            </div>
            {library.length === 0 ? (
              <p className="m-0 text-xs text-muted-foreground">
                Nenhum motion importado ainda. Arraste um arquivo <code>.html</code> ou clique em &ldquo;+ Carregar Exemplo v1&rdquo;.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2" data-testid="motion-library-list">
                {library.map((item) => (
                  <div
                    key={item.key}
                    className="flex items-center gap-2 rounded border border-border bg-secondary px-2.5 py-1.5 text-xs"
                  >
                    <span>
                      <b>{item.name}</b>{" "}
                      <code className="text-muted-foreground">
                        {item.id}@{item.version}
                      </code>
                    </span>
                    <button
                      type="button"
                      className="btn btn-accent btn-small"
                      onClick={() => launchMotionSlot(item.key)}
                    >
                      ▶ Executar
                    </button>
                    <button
                      type="button"
                      aria-label={`Remover ${item.key} da biblioteca`}
                      className="btn btn-small"
                      onClick={() => {
                        setSlots((cur) => cur.filter((s) => s.motionKey !== item.key));
                        persistLibrary(library.filter((x) => x.key !== item.key));
                      }}
                    >
                      Excluir
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* 6. ÁUDIO CENTRAL */}
          <section className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/30 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="text-xs uppercase tracking-wider text-muted-foreground">
                6. Áudio Central (AudioContext + AnalyserNode único → todos os motions em sincronia)
              </strong>
              <div className="flex flex-wrap items-center gap-2">
                <label className="btn btn-small cursor-pointer">
                  🎵 Arquivo de áudio
                  <input
                    type="file"
                    accept="audio/*"
                    hidden
                    onChange={(e) => e.target.files?.[0] && startAudioFile(e.target.files[0])}
                  />
                </label>
                <button
                  type="button"
                  className={`btn btn-small ${audioSourceKind === "mic" ? "btn-accent" : ""}`}
                  onClick={() => void startMicOrLine("mic")}
                >
                  🎙 Microfone
                </button>
                <button
                  type="button"
                  className={`btn btn-small ${audioSourceKind === "line" ? "btn-accent" : ""}`}
                  onClick={() => void startMicOrLine("line", lineDeviceId || undefined)}
                >
                  🔌 Entrada de linha
                </button>
                {audioDevices.length > 0 && (
                  <select
                    aria-label="Dispositivo de entrada de linha"
                    value={lineDeviceId}
                    onChange={(e) => {
                      setLineDeviceId(e.target.value);
                      if (audioSourceKind === "line") void startMicOrLine("line", e.target.value);
                    }}
                    className="rounded border border-border bg-secondary px-2 py-1 text-xs"
                  >
                    <option value="">Entrada padrão</option>
                    {audioDevices.map((d) => (
                      <option key={d.deviceId} value={d.deviceId}>
                        {d.label || `Entrada ${d.deviceId.slice(0, 6)}`}
                      </option>
                    ))}
                  </select>
                )}
                {audioSourceKind !== "none" && (
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => {
                      stopAudioSource();
                      setAudioSourceKind("none");
                    }}
                  >
                    Parar áudio
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={simulatePulseBeat}
                  title="Envia um quadro motion:audio com beat=1 para todos os motions ativos"
                >
                  🥁 Pulso de Beat (Teste)
                </button>
              </div>
            </div>

            <div className="grid grid-cols-5 gap-2 text-xs" data-testid="central-audio-meters">
              <div>
                Bass (25–140 Hz): <b>{audioFrame.bass.toFixed(2)}</b>
              </div>
              <div>
                Mid (250–2200 Hz): <b>{audioFrame.mid.toFixed(2)}</b>
              </div>
              <div>
                High (4–12 kHz): <b>{audioFrame.high.toFixed(2)}</b>
              </div>
              <div>
                Level: <b>{audioFrame.level.toFixed(2)}</b>
              </div>
              <div>
                Beat: <b>{audioFrame.beat.toFixed(2)}</b> (total: <span data-testid="central-beat-count">{beatCount}</span>)
              </div>
            </div>
          </section>

          {/* 7. EVENTOS, ESTADO E REGRAS DE AUTOMAÇÃO */}
          <section className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/30 p-3">
            <strong className="text-xs uppercase tracking-wider text-muted-foreground">
              7. Regras de Automação (Fase & Beat)
            </strong>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <select
                aria-label="Tipo de regra"
                value={ruleKind}
                onChange={(e) => setRuleKind(e.target.value as "phase_switch" | "beat_trigger")}
                className="rounded border border-border bg-secondary px-2 py-1"
              >
                <option value="phase_switch">Quando phase = X, trocar para o motion Y</option>
                <option value="beat_trigger">Trigger X a cada N beats</option>
              </select>

              {ruleKind === "phase_switch" ? (
                <>
                  <label className="flex items-center gap-1">
                    phase =
                    <input
                      type="text"
                      aria-label="Valor da fase"
                      value={rulePhase}
                      onChange={(e) => setRulePhase(e.target.value)}
                      className="w-24 rounded border border-border bg-secondary px-1.5 py-0.5"
                    />
                  </label>
                  <label className="flex items-center gap-1">
                    trocar para:
                    <select
                      aria-label="Motion alvo da regra"
                      value={ruleTargetMotion || library[0]?.key || ""}
                      onChange={(e) => setRuleTargetMotion(e.target.value)}
                      className="rounded border border-border bg-secondary px-2 py-1"
                    >
                      {library.map((m) => (
                        <option key={m.key} value={m.key}>
                          {m.name} ({m.key})
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              ) : (
                <>
                  <label className="flex items-center gap-1">
                    trigger
                    <input
                      type="text"
                      aria-label="ID do trigger da regra"
                      value={ruleTriggerId}
                      onChange={(e) => setRuleTriggerId(e.target.value)}
                      className="w-24 rounded border border-border bg-secondary px-1.5 py-0.5"
                    />
                  </label>
                  <label className="flex items-center gap-1">
                    a cada
                    <input
                      type="number"
                      aria-label="A cada N beats"
                      min={1}
                      max={256}
                      value={ruleEveryBeats}
                      onChange={(e) => setRuleEveryBeats(Math.max(1, Number(e.target.value) || 1))}
                      className="w-16 rounded border border-border bg-secondary px-1.5 py-0.5"
                    />
                    beats
                  </label>
                </>
              )}

              <button type="button" className="btn btn-small" onClick={addRule}>
                + Adicionar Regra
              </button>
            </div>

            {rules.length > 0 && (
              <ul className="flex flex-wrap gap-2 text-xs" data-testid="motion-rules-list">
                {rules.map((r) => (
                  <li key={r.id} className="inline-flex items-center gap-2 rounded border border-border bg-secondary px-2 py-1">
                    <input
                      type="checkbox"
                      checked={r.enabled}
                      aria-label={`Ativar regra ${r.id}`}
                      onChange={(e) =>
                        persistRules(rules.map((x) => (x.id === r.id ? { ...x, enabled: e.target.checked } : x)))
                      }
                    />
                    <span>
                      {r.kind === "phase_switch"
                        ? `Quando phase = "${r.whenPhase}" → trocar para ${r.targetMotionKey}`
                        : `Trigger "${r.triggerId}" a cada ${r.everyNBeats} beat(s)`}
                    </span>
                    <button
                      type="button"
                      aria-label={`Remover regra ${r.id}`}
                      onClick={() => persistRules(rules.filter((x) => x.id !== r.id))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* 3. EXECUÇÃO + 4. PAINEL AUTOMÁTICO + 5. PRESETS + 8. CICLO DE VIDA */}
          <section className="flex flex-col gap-3">
            <strong className="text-xs uppercase tracking-wider text-muted-foreground">
              3 & 4. Motions Ativos ({slots.length})
            </strong>
            {slots.length === 0 ? (
              <p className="m-0 text-xs text-muted-foreground">
                Nenhum motion em execução. Clique em <b>▶ Executar</b> em um item da biblioteca acima (você pode abrir vários ao mesmo tempo para reagirem juntos ao áudio central).
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {slots.map((slot) => {
                  const entry = library.find((m) => m.key === slot.motionKey);
                  if (!entry) return null;
                  return (
                    <MotionSlotRunner
                      key={slot.slotId}
                      slotId={slot.slotId}
                      entry={entry}
                      presets={presets}
                      beatActive={audioFrame.beat >= 0.5}
                      onSavePreset={(p) => persistPresets([...presets, p])}
                      onDeletePreset={(id) => persistPresets(presets.filter((x) => x.id !== id))}
                      onPhaseChange={handlePhaseChange}
                      onRemoveSlot={removeSlot}
                      registerHandle={registerHandle}
                    />
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
