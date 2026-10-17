"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import {
  applyMotionPreset,
  computeAudioFrame,
  createBeatDetectorState,
  defaultParamsForManifest,
  EMPTY_AUDIO_FRAME,
  findExistingById,
  groupManifestParams,
  motionKey,
  parseAndValidateMotionHtml,
  REACT_TO_OPTIONS,
  realignDownbeatOnNextBeat,
  recalibrateAgc,
  registerTapTempo,
  runMotionSmokeTest,
  SAMPLE_MOTION_HTML,
  triggerManualBeat,
  upsertMotionInLibrary,
  validateGeneratedMotionStrict,
  type MotionAudioFrame,
  type MotionGenerationRecord,
  type MotionLibraryEntry,
  type MotionManifest,
  type MotionParamDef,
  type MotionParamValue,
  type MotionPreset,
  type MotionRule,
  type MotionValidationError,
  type ReactToMacro,
  type SmokeTestResult,
  type Vec3,
} from "../lib/motionModule";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";

const LIB_STORAGE_KEY = "projmap.motions.library.v1";
const PRESETS_STORAGE_KEY = "projmap.motions.presets.v1";
const RULES_STORAGE_KEY = "projmap.motions.rules.v1";
const READY_TIMEOUT_MS = 5000;

export const CLAUDE_SUGGESTIONS = [
  "anéis de luz que explodem no kick",
  "partículas que seguem os agudos",
  "líquido metálico que pulsa com os graves",
];

export interface ActiveMotionSlot {
  slotId: string;
  motionKey: string;
}

interface PendingConflict {
  manifest: MotionManifest;
  html: string;
  existingVersions: string[];
  notes?: string;
  generationRecord?: MotionGenerationRecord;
  layerPreset?: Record<string, unknown>;
}

export interface MotionHandle {
  postAudio: (frame: MotionAudioFrame) => void;
  postTrigger: (triggerId: string) => void;
  applyReactTo: (macro: ReactToMacro) => void;
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

function signalValueFromFrame(frame: MotionAudioFrame, src: string): number {
  const map: Record<string, number> = {
    bass: frame.bass,
    mid: frame.mid,
    high: frame.high,
    level: frame.level,
    energy: frame.energy,
    kick: frame.kick,
    snare: frame.snare,
    hat: frame.hat,
    beat: frame.beat,
    downbeat: frame.downbeat,
    off: 0,
  };
  return map[src] ?? 0;
}

interface MotionSlotRunnerProps {
  slotId: string;
  entry: MotionLibraryEntry;
  presets: MotionPreset[];
  audioFrame: MotionAudioFrame;
  isSelected: boolean;
  onSelectSlot: (slotId: string) => void;
  onApplyReactToAll: (macro: ReactToMacro) => void;
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
  audioFrame,
  isSelected,
  onSelectSlot,
  onApplyReactToAll,
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

  // 4. PAINEL AUTOMÁTICO: cada alteração envia motion:setParams na hora
  const updateParam = useCallback(
    (key: string, value: MotionParamValue) => {
      setParams((prev) => {
        const next = { ...prev, [key]: value };
        postToMotion("motion:setParams", next);
        return next;
      });
    },
    [postToMotion],
  );

  // Expõe handle para o áudio central, triggers automáticos de beat e "Aplicar reactTo a todas as camadas"
  useEffect(() => {
    registerHandle(slotId, {
      postAudio: (frame) => postToMotion("motion:audio", frame),
      postTrigger: (triggerId) => postToMotion("motion:trigger", { id: triggerId, name: triggerId }),
      applyReactTo: (macro) => {
        if (manifest.params.reactTo) {
          updateParam("reactTo", macro);
        }
      },
    });
    return () => registerHandle(slotId, null);
  }, [slotId, manifest.params.reactTo, postToMotion, registerHandle, updateParam]);

  // B.4 Atalho por camada: teclas 1–5 com a camada selecionada trocam o reactTo entre as cinco opções
  useEffect(() => {
    if (!isSelected || !manifest.params.reactTo) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const idx = ["1", "2", "3", "4", "5"].indexOf(e.key);
      if (idx >= 0) {
        e.preventDefault();
        const chosen = REACT_TO_OPTIONS[idx].value;
        updateParam("reactTo", chosen);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isSelected, manifest.params.reactTo, updateParam]);

  // 3. EXECUÇÃO + 8. CICLO DE VIDA
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
      } else if (type === "motion:error") {
        setStatus("error");
        setErrorMsg(String(payload?.message ?? "Erro reportado pelo motion"));
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
  const currentReactTo = (params.reactTo as ReactToMacro) ?? "mix";
  const beatActive = audioFrame.beat >= 0.5;

  return (
    <div
      onClick={() => onSelectSlot(slotId)}
      className={`flex flex-col gap-3 rounded-lg border p-3 transition ${
        isSelected ? "border-primary bg-secondary/50" : "border-border bg-secondary/30"
      }`}
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
            onClick={(e) => {
              e.stopPropagation();
              cleanupMotionInstance();
              onRemoveSlot(slotId);
            }}
            title="Enviar motion:destroy, remover iframe e revogar blob URL"
          >
            Remover Motion
          </button>
        </div>
      </div>

      {/* Notas do motion (alvos de reação e fontes sugeridas, C.5) */}
      {entry.notes && (
        <div className="rounded border border-border bg-secondary/50 px-2.5 py-1.5 text-xs text-muted-foreground">
          <b>Notas do Motion:</b> {entry.notes}
        </div>
      )}

      {errorMsg && (
        <div role="alert" className="rounded border border-red-500/50 bg-red-950/40 p-2 text-xs text-red-200">
          {errorMsg}
        </div>
      )}

      {/* B.1 & B.5 Controle segmentado grande de reactTo no topo do painel da camada */}
      {manifest.params.reactTo && (
        <div
          className="flex flex-col gap-2 rounded-md border border-border bg-secondary/60 p-2.5"
          data-testid={`reaction-topbar-${slotId}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold text-foreground">
              🎛 Reação ao Áudio (Teclas 1–5 com a camada selecionada)
            </span>
            <button
              type="button"
              className="btn btn-small"
              onClick={() => onApplyReactToAll(currentReactTo)}
              title="Muda o reactTo de todas as camadas ativas de uma vez (ex.: num drop)"
            >
              Aplicar reactTo a todas as camadas
            </button>
          </div>
          <div className="segmented flex w-full" role="group" aria-label="Macro reactTo">
            {REACT_TO_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`flex-1 py-1.5 text-xs font-semibold ${currentReactTo === opt.value ? "on" : ""}`}
                onClick={() => updateParam("reactTo", opt.value)}
                data-testid={`react-to-btn-${opt.value}-${slotId}`}
              >
                [{opt.shortcut}] {opt.label}
              </button>
            ))}
          </div>
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

      {/* Painel Automático agrupado por "group" (com tratamento especial para Reação ao áudio) */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {Object.entries(groups).map(([groupName, groupDefs]) => (
          <fieldset key={groupName} className="flex flex-col gap-2 rounded border border-border p-2.5">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">{groupName}</legend>
            {groupDefs.map((def) => {
              const isRxSrc = /^rx_[a-zA-Z0-9_]+_src$/.test(def.key);
              const disabledRxSrc = isRxSrc && currentReactTo !== "custom";
              const selectedSrc = isRxSrc ? String(params[def.key] ?? def.default) : null;
              const liveVal = selectedSrc ? signalValueFromFrame(audioFrame, selectedSrc) : 0;

              return (
                <div key={def.key} className={disabledRxSrc ? "opacity-55" : ""}>
                  <ParamControl
                    def={def}
                    value={params[def.key] ?? def.default}
                    disabled={disabledRxSrc}
                    onChange={(val) => updateParam(def.key, val)}
                  />
                  {/* B.2 Mini medidor ao vivo ao lado de cada rx_<alvo>_src */}
                  {isRxSrc && selectedSrc && (
                    <div
                      className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground"
                      data-testid={`rx-meter-${def.key}-${slotId}`}
                    >
                      <span>Sinal ({selectedSrc}):</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded bg-black/50">
                        <div
                          className="h-full bg-purple-500 transition-all"
                          style={{ width: `${Math.round(liveVal * 100)}%` }}
                        />
                      </div>
                      <span className="w-8 text-right">{Math.round(liveVal * 100)}%</span>
                    </div>
                  )}
                </div>
              );
            })}
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
  disabled = false,
  onChange,
}: {
  def: MotionParamDef;
  value: MotionParamValue;
  disabled?: boolean;
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
            disabled={disabled}
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
          disabled={disabled}
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
          disabled={disabled}
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
          disabled={disabled}
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
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="rounded border border-border bg-secondary px-2 py-1 text-xs text-foreground disabled:cursor-not-allowed"
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
              disabled={disabled}
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
              disabled={disabled}
              onChange={(e) => setAxis(i, e.target.value)}
              className="w-16 rounded border border-border bg-secondary px-1 py-0.5 text-right text-xs"
            />
          </div>
        );
      })}
    </div>
  );
}

export type ClaudeStreamGenerator = (
  body: {
    kind: "new" | "edit" | "repair";
    prompt?: string;
    current_html?: string;
    errors?: string[];
    images?: { media_type: string; data: string }[];
    model?: string;
  },
  onProgress: (ev: { elapsed_s: number; tokens_received: number; section: string }) => void,
  signal?: AbortSignal,
) => Promise<{
  ok: boolean;
  html: string;
  layer_preset: Record<string, unknown>;
  notes: string;
  errors: string[];
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens: number;
    cache_read_input_tokens: number;
    estimated_cost_usd: number;
  };
}>;

interface MotionStudioDialogProps {
  open: boolean;
  onClose: () => void;
  /** Permite injetar mock do gerador Claude e do smoke test em testes unitários (C.6). */
  claudeGenerator?: ClaudeStreamGenerator;
  smokeTestRunner?: (html: string, layerPreset?: Record<string, unknown>) => Promise<SmokeTestResult>;
}

export default function MotionStudioDialog({
  open,
  onClose,
  claudeGenerator = api.motionAiGenerateStream,
  smokeTestRunner = runMotionSmokeTest,
}: MotionStudioDialogProps) {
  const [studioTab, setStudioTab] = useState<"studio" | "claude">("studio");
  const [library, setLibrary] = useState<MotionLibraryEntry[]>([]);
  const [presets, setPresets] = useState<MotionPreset[]>([]);
  const [rules, setRules] = useState<MotionRule[]>([]);
  const [slots, setSlots] = useState<ActiveMotionSlot[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<MotionValidationError[]>([]);
  const [pendingConflict, setPendingConflict] = useState<PendingConflict | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // A. MOTOR DE ÁUDIO PARA DJ
  const [audioSourceKind, setAudioSourceKind] = useState<"none" | "file" | "mic" | "line">("none");
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [lineDeviceId, setLineDeviceId] = useState<string>("");
  const [audioFrame, setAudioFrame] = useState<MotionAudioFrame>(EMPTY_AUDIO_FRAME);
  const [beatCount, setBeatCount] = useState<number>(0);
  const [bpmLocked, setBpmLocked] = useState<boolean>(false);
  const [gainTrimDb, setGainTrimDb] = useState<number>(0);
  const [anticipationMs, setAnticipationMs] = useState<number>(0);

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

  // C. GERAR MOTION COM CLAUDE
  const [aiConfigured, setAiConfigured] = useState<boolean>(false);
  const [aiModel, setAiModel] = useState<string>("claude-opus-5-5");
  const [aiKeyInput, setAiKeyInput] = useState<string>("");
  const [aiMode, setAiMode] = useState<"new" | "edit">("new");
  const [aiEditTargetKey, setAiEditTargetKey] = useState<string>("");
  const [aiPrompt, setAiPrompt] = useState<string>("");
  const [aiImages, setAiImages] = useState<{ name: string; media_type: string; data: string }[]>([]);
  const [aiBusy, setAiBusy] = useState<boolean>(false);
  const [aiStatusMsg, setAiStatusMsg] = useState<string>("");
  const [aiProgress, setAiProgress] = useState<{ elapsed_s: number; tokens_received: number; section: string } | null>(null);
  const [aiLastUsage, setAiLastUsage] = useState<{
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens: number;
    cache_read_input_tokens: number;
    estimated_cost_usd: number;
  } | null>(null);
  const [aiDraftFailure, setAiDraftFailure] = useState<{
    html: string;
    layerPreset: Record<string, unknown>;
    notes: string;
    errors: string[];
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const savedLib = loadStoredJson<MotionLibraryEntry[]>(LIB_STORAGE_KEY, []);
    const savedPresets = loadStoredJson<MotionPreset[]>(PRESETS_STORAGE_KEY, []);
    const savedRules = loadStoredJson<MotionRule[]>(RULES_STORAGE_KEY, []);
    setLibrary(savedLib);
    setPresets(savedPresets);
    setRules(savedRules);
  }, []);

  useEffect(() => {
    if (!open) return;
    api
      .motionAiConfig()
      .then((cfg) => {
        setAiConfigured(cfg.configured);
        setAiModel(cfg.model || "claude-opus-5-5");
      })
      .catch(() => {});
  }, [open]);

  const persistLibrary = useCallback((next: MotionLibraryEntry[]) => {
    setLibrary(next);
    saveStoredJson(LIB_STORAGE_KEY, next);
  }, []);

  const persistPresets = useCallback((next: MotionPreset[]) => {
    setPresets(next);
    saveStoredJson(PRESETS_STORAGE_KEY, next);
  }, []);

  const persistRules = (next: MotionRule[]) => {
    setRules(next);
    saveStoredJson(RULES_STORAGE_KEY, next);
  };

  const registerHandle = useCallback((slotId: string, handle: MotionHandle | null) => {
    if (handle) handlesRef.current.set(slotId, handle);
    else handlesRef.current.delete(slotId);
  }, []);

  // Salva o layer_preset como preset "Camada" do motion (C.5)
  const saveLayerPresetForMotion = useCallback(
    (manifest: MotionManifest, layerPreset?: Record<string, unknown>) => {
      if (!layerPreset || typeof layerPreset !== "object") return;
      const rawParams =
        typeof layerPreset.params === "object" && layerPreset.params !== null
          ? (layerPreset.params as Record<string, unknown>)
          : { framing: "element", background: "transparent" };
      const mode = typeof layerPreset.mode === "string" ? layerPreset.mode : (manifest.modes[0]?.id ?? "default");
      const newPreset: MotionPreset = {
        id: `preset-camada-${manifest.id}-${manifest.version}`,
        name: "Camada",
        motionId: manifest.id,
        motionVersion: manifest.version,
        mode,
        params: rawParams,
        createdAt: new Date().toISOString(),
      };
      setPresets((cur) => {
        const next = [...cur.filter((p) => p.id !== newPreset.id), newPreset];
        saveStoredJson(PRESETS_STORAGE_KEY, next);
        return next;
      });
    },
    [],
  );

  // 1. IMPORTAÇÃO + 2. BIBLIOTECA
  const importHtmlContent = useCallback(
    (
      htmlText: string,
      extra?: {
        notes?: string;
        generationRecord?: MotionGenerationRecord;
        layerPreset?: Record<string, unknown>;
        skipValidation?: boolean;
      },
    ) => {
      setValidationErrors([]);
      setPendingConflict(null);
      const res = parseAndValidateMotionHtml(htmlText);
      if (!res.ok) {
        setValidationErrors(res.errors);
        return false;
      }
      if (extra?.layerPreset) {
        saveLayerPresetForMotion(res.manifest, extra.layerPreset);
      }
      const existing = findExistingById(library, res.manifest.id);
      if (existing.length > 0) {
        setPendingConflict({
          manifest: res.manifest,
          html: res.html,
          existingVersions: existing.map((e) => e.version),
          notes: extra?.notes,
          generationRecord: extra?.generationRecord,
          layerPreset: extra?.layerPreset,
        });
        return true;
      }
      const nextLib = upsertMotionInLibrary(library, res.manifest, res.html, "keep_both", {
        notes: extra?.notes,
        generationRecord: extra?.generationRecord,
      });
      persistLibrary(nextLib);
      const key = motionKey(res.manifest.id, res.manifest.version);
      if (slots.length === 0) {
        const sid = `slot-${Date.now()}`;
        setSlots([{ slotId: sid, motionKey: key }]);
        setSelectedSlotId(sid);
      }
      return true;
    },
    [library, persistLibrary, saveLayerPresetForMotion, slots.length],
  );

  const resolveConflict = (resolution: "replace" | "keep_both") => {
    if (!pendingConflict) return;
    const { manifest, html, notes, generationRecord } = pendingConflict;
    const nextLib = upsertMotionInLibrary(library, manifest, html, resolution, { notes, generationRecord });
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
    const sid = `slot-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setSlots((cur) => [...cur, { slotId: sid, motionKey: key }]);
    setSelectedSlotId(sid);
  };

  const removeSlot = useCallback((slotId: string) => {
    setSlots((cur) => cur.filter((s) => s.slotId !== slotId));
  }, []);

  // B.5 Aplicar reactTo a todas as camadas
  const applyReactToAllLayers = useCallback((macro: ReactToMacro) => {
    handlesRef.current.forEach((h) => h.applyReactTo(macro));
  }, []);

  // 7. EVENTOS E ESTADO: aplica regra "quando phase = X, trocar para o motion Y"
  const handlePhaseChange = useCallback((slotId: string, newPhase: string) => {
    for (const r of rulesRef.current) {
      if (r.enabled && r.kind === "phase_switch" && r.whenPhase === newPhase) {
        setSlots((cur) =>
          cur.map((s) => (s.slotId === slotId && s.motionKey !== r.targetMotionKey ? { ...s, motionKey: r.targetMotionKey } : s)),
        );
        break;
      }
    }
  }, []);

  // Dispara frame de áudio para todos os motions ativos e executa regras de N beats
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

  // Atalhos de teclado globais do DJ: T = Tap Tempo, B = Batida manual (A.2)
  const handleTapTempo = useCallback(() => {
    const newBpm = registerTapTempo(beatStateRef.current, performance.now());
    setBpmLocked(beatStateRef.current.bpmLocked);
    setAudioFrame((prev) => ({ ...prev, bpm: newBpm }));
  }, []);

  const handleManualBeat = useCallback(() => {
    triggerManualBeat(beatStateRef.current);
    beatStateRef.current.beatCount += 1;
    const total = beatStateRef.current.beatCount;
    setBeatCount(total);
    const frame: MotionAudioFrame = {
      ...audioFrame,
      bass: Math.max(audioFrame.bass, 0.92),
      level: Math.max(audioFrame.level, 0.85),
      kick: 1,
      beat: 1,
      downbeat: total % 4 === 1 ? 1 : 0,
      bpm: beatStateRef.current.bpm,
    };
    setAudioFrame(frame);
    dispatchBeat(frame, true, total);
  }, [audioFrame, dispatchBeat]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "t" || e.key === "T") {
        e.preventDefault();
        handleTapTempo();
      } else if (e.key === "b" || e.key === "B") {
        e.preventDefault();
        handleManualBeat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleTapTempo, handleManualBeat]);

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
        beatStateRef.current.gainTrimDb = gainTrimDb;
        beatStateRef.current.anticipationMs = anticipationMs;
        const { frame, triggered } = computeAudioFrame(
          freqBuf,
          timeBuf,
          ctx.sampleRate || 44100,
          an.fftSize || 2048,
          beatStateRef.current,
          nowMs,
        );
        setAudioFrame(frame);
        setBpmLocked(beatStateRef.current.bpmLocked);
        if (triggered) {
          setBeatCount(beatStateRef.current.beatCount);
        }
        dispatchBeat(frame, triggered, beatStateRef.current.beatCount);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [open, audioSourceKind, gainTrimDb, anticipationMs, dispatchBeat]);

  useEffect(() => {
    return () => stopAudioSource();
  }, [stopAudioSource]);

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

  // ==========================================================================
  // C.3, C.4, C.5 GERAÇÃO DE MOTION COM CLAUDE + LOOP DE VALIDAÇÃO E REPARO (ATÉ 3 TENTATIVAS)
  // ==========================================================================
  const handleAddReferenceImages = async (files: FileList | null) => {
    if (!files) return;
    const added: { name: string; media_type: string; data: string }[] = [];
    for (let i = 0; i < files.length && aiImages.length + added.length < 4; i++) {
      const f = files[i];
      const buf = await f.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      for (let j = 0; j < bytes.length; j++) binary += String.fromCharCode(bytes[j]);
      const base64 = btoa(binary);
      added.push({ name: f.name, media_type: f.type || "image/png", data: base64 });
    }
    setAiImages((prev) => [...prev, ...added].slice(0, 4));
  };

  const handleSaveAiConfig = async () => {
    try {
      const status = await api.motionAiSetConfig({
        api_key: aiKeyInput.trim() ? aiKeyInput.trim() : undefined,
        model: aiModel,
      });
      setAiConfigured(status.configured);
      setAiModel(status.model);
      setAiKeyInput("");
    } catch {
      /* ignore */
    }
  };

  const runClaudeGenerationLoop = async () => {
    if (!aiPrompt.trim()) return;
    setAiBusy(true);
    setAiDraftFailure(null);
    setAiProgress(null);
    setAiStatusMsg(aiMode === "new" ? "Gerando motion com Claude…" : "Editando motion com Claude…");

    const controller = new AbortController();
    abortRef.current = controller;

    // Para "Editar", parte sempre da última versão do motion na biblioteca (C.5)
    const editEntry = library.find((m) => m.key === (aiEditTargetKey || library[library.length - 1]?.key));
    let currentKind: "new" | "edit" | "repair" = aiMode;
    let currentHtml = aiMode === "edit" && editEntry ? editEntry.html : "";
    let currentErrors: string[] = [];
    let lastHtml = "";
    let lastPreset: Record<string, unknown> = {};
    let lastNotes = "";
    let totalUsage = {
      input_tokens: 0,
      output_tokens: 0,
      cache_creation_input_tokens: 0,
      cache_read_input_tokens: 0,
      estimated_cost_usd: 0,
    };

    try {
      // Tentativa inicial (attempt=0) + até 3 tentativas de reparo (attempts 1, 2, 3)
      for (let attempt = 0; attempt <= 3; attempt++) {
        if (attempt > 0) {
          currentKind = "repair";
          setAiStatusMsg(`Corrigindo (tentativa ${attempt} de 3)…`);
        }

        const res = await claudeGenerator(
          {
            kind: currentKind,
            prompt: currentKind === "repair" ? "" : aiPrompt.trim(),
            current_html: currentHtml,
            errors: currentErrors,
            images: currentKind === "new" ? aiImages.map(({ media_type, data }) => ({ media_type, data })) : [],
            model: aiModel,
          },
          (prog) => setAiProgress(prog),
          controller.signal,
        );

        if (res.usage) {
          totalUsage = {
            input_tokens: totalUsage.input_tokens + (res.usage.input_tokens || 0),
            output_tokens: totalUsage.output_tokens + (res.usage.output_tokens || 0),
            cache_creation_input_tokens:
              totalUsage.cache_creation_input_tokens + (res.usage.cache_creation_input_tokens || 0),
            cache_read_input_tokens: totalUsage.cache_read_input_tokens + (res.usage.cache_read_input_tokens || 0),
            estimated_cost_usd:
              Math.round((totalUsage.estimated_cost_usd + (res.usage.estimated_cost_usd || 0)) * 10000) / 10000,
          };
          setAiLastUsage(totalUsage);
        }

        lastHtml = res.html || currentHtml;
        lastPreset = res.layer_preset || {};
        lastNotes = res.notes || "";

        const stepErrors: string[] = [];
        if (!res.ok || res.errors?.length) {
          stepErrors.push(...(res.errors || ["Resposta incompleta do modelo."]));
        }

        // C.4 Etapa 1: Validação estática estrita
        if (res.html) {
          const staticRes = validateGeneratedMotionStrict(res.html);
          if (!staticRes.ok) {
            stepErrors.push(...staticRes.errors.map((e) => `${e.field}: ${e.message}`));
          }
        } else {
          stepErrors.push("HTML vazio retornado pelo gerador.");
        }

        // C.4 Etapa 2: Teste de fumaça em execução (iframe 480x480)
        if (stepErrors.length === 0 && res.html) {
          setAiStatusMsg("Executando teste de fumaça (480×480)…");
          const smoke = await smokeTestRunner(res.html, res.layer_preset);
          if (!smoke.ok) {
            stepErrors.push(...smoke.errors);
          }
        }

        if (stepErrors.length === 0) {
          // C.5 Sucesso!
          const record: MotionGenerationRecord = {
            timestamp: new Date().toISOString(),
            kind: aiMode,
            prompt: aiPrompt.trim(),
            imagesCount: aiImages.length,
            notes: lastNotes,
            usage: totalUsage,
          };
          importHtmlContent(lastHtml, {
            notes: lastNotes,
            generationRecord: record,
            layerPreset: lastPreset,
          });
          setAiStatusMsg("Motion validado e importado com sucesso!");
          setStudioTab("studio");
          setAiBusy(false);
          return;
        }

        currentHtml = lastHtml;
        currentErrors = stepErrors;
      }

      // Depois de 3 tentativas de reparo sem sucesso (C.4 item 4):
      setAiDraftFailure({
        html: lastHtml,
        layerPreset: lastPreset,
        notes: lastNotes,
        errors: currentErrors,
      });
      setAiStatusMsg("Falha após 3 tentativas de reparo automático.");
    } catch (e) {
      if ((e as Error)?.name === "AbortError") {
        setAiStatusMsg("Geração cancelada pelo usuário.");
      } else {
        setAiStatusMsg(e instanceof Error ? e.message : "Erro na geração com Claude.");
      }
    } finally {
      setAiBusy(false);
      abortRef.current = null;
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent aria-label="Motion Module v1 Studio" className="max-h-[92vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-3">
            <DialogTitle>🎬 Motion Module v1 — Host DJ & Gerador Claude</DialogTitle>
            <div className="segmented">
              <button
                type="button"
                className={studioTab === "studio" ? "on" : ""}
                onClick={() => setStudioTab("studio")}
              >
                🎛 Biblioteca & Host Ao Vivo
              </button>
              <button
                type="button"
                className={studioTab === "claude" ? "on" : ""}
                onClick={() => setStudioTab("claude")}
                data-testid="tab-generate-claude"
              >
                ✨ Gerar com Claude
              </button>
            </div>
          </div>
          <button type="button" className="btn btn-small" onClick={onClose}>
            Fechar
          </button>
        </DialogHeader>

        {studioTab === "claude" ? (
          <div className="flex flex-col gap-4" data-testid="claude-generator-panel">
            {/* Configuração da chave e modelo (salva no keyring do backend, C.1) */}
            <section className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-secondary/30 p-3 text-xs">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-2 py-0.5 font-semibold ${
                    aiConfigured ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300"
                  }`}
                >
                  {aiConfigured ? "✓ Chave Anthropic configurada (backend/keyring)" : "Chave Anthropic pendente"}
                </span>
                <label className="flex items-center gap-1">
                  Modelo:
                  <input
                    type="text"
                    aria-label="Modelo Claude"
                    value={aiModel}
                    onChange={(e) => setAiModel(e.target.value)}
                    className="w-40 rounded border border-border bg-secondary px-2 py-1 text-xs"
                  />
                </label>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="password"
                  placeholder="Nova ANTHROPIC_API_KEY (salva no keyring)…"
                  aria-label="Chave da API Anthropic"
                  value={aiKeyInput}
                  onChange={(e) => setAiKeyInput(e.target.value)}
                  className="w-64 rounded border border-border bg-secondary px-2 py-1 text-xs"
                />
                <button type="button" className="btn btn-small" onClick={() => void handleSaveAiConfig()}>
                  Salvar Configuração
                </button>
              </div>
            </section>

            {/* Tipo de pedido: Novo vs Editar (C.3) */}
            <section className="flex flex-col gap-3 rounded-lg border border-border bg-secondary/40 p-3">
              <div className="flex flex-wrap items-center gap-3">
                <div className="segmented">
                  <button
                    type="button"
                    className={aiMode === "new" ? "on" : ""}
                    onClick={() => setAiMode("new")}
                  >
                    [NOVO] Criar do zero
                  </button>
                  <button
                    type="button"
                    className={aiMode === "edit" ? "on" : ""}
                    onClick={() => setAiMode("edit")}
                    disabled={library.length === 0}
                  >
                    [EDITAR] A partir da biblioteca
                  </button>
                </div>

                {aiMode === "edit" && library.length > 0 && (
                  <label className="flex items-center gap-1.5 text-xs">
                    Motion base:
                    <select
                      aria-label="Motion base para edição"
                      value={aiEditTargetKey || library[library.length - 1]?.key || ""}
                      onChange={(e) => setAiEditTargetKey(e.target.value)}
                      className="rounded border border-border bg-secondary px-2 py-1 text-xs"
                    >
                      {library.map((m) => (
                        <option key={m.key} value={m.key}>
                          {m.name} ({m.key})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>

              <label className="flex flex-col gap-1 text-xs">
                <span className="font-semibold">
                  {aiMode === "new" ? "Descrição do visual áudio-reativo:" : "O que mudar?"}
                </span>
                <textarea
                  rows={3}
                  aria-label={aiMode === "new" ? "Descrição do motion" : "O que mudar"}
                  placeholder={
                    aiMode === "new"
                      ? "Descreva o elemento visual, estética, cores e reação ao som…"
                      : "Descreva as alterações desejadas mantendo o mesmo id…"
                  }
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  className="w-full rounded border border-border bg-secondary p-2 text-xs text-foreground"
                />
              </label>

              {/* Sugestões clicáveis quando o campo está vazio (C.3) */}
              {!aiPrompt.trim() && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs" data-testid="claude-suggestions">
                  <span className="text-muted-foreground">Sugestões:</span>
                  {CLAUDE_SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="btn btn-small"
                      onClick={() => setAiPrompt(s)}
                    >
                      “{s}”
                    </button>
                  ))}
                </div>
              )}

              {aiMode === "new" && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <label className="btn btn-small cursor-pointer">
                    🖼 + Imagens de referência ({aiImages.length}/4)
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      hidden
                      onChange={(e) => void handleAddReferenceImages(e.target.files)}
                    />
                  </label>
                  {aiImages.map((img, i) => (
                    <span key={i} className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-0.5">
                      {img.name}
                      <button
                        type="button"
                        onClick={() => setAiImages((cur) => cur.filter((_, idx) => idx !== i))}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn btn-accent"
                  disabled={aiBusy || !aiPrompt.trim()}
                  onClick={() => void runClaudeGenerationLoop()}
                  data-testid="btn-run-claude"
                >
                  {aiBusy ? "Gerando…" : aiMode === "new" ? "✨ Gerar Motion com Claude" : "✨ Aplicar Edição com Claude"}
                </button>
                {aiBusy && (
                  <button
                    type="button"
                    className="btn btn-danger btn-small"
                    onClick={() => abortRef.current?.abort()}
                  >
                    Cancelar
                  </button>
                )}
                {aiStatusMsg && (
                  <span className="text-xs font-medium text-foreground" data-testid="claude-status-msg">
                    {aiStatusMsg}
                  </span>
                )}
              </div>

              {aiProgress && (
                <div className="text-xs text-muted-foreground" data-testid="claude-stream-progress">
                  Tempo: <b>{aiProgress.elapsed_s}s</b> · Tokens recebidos: <b>{aiProgress.tokens_received}</b> · Seção:{" "}
                  <b>{aiProgress.section}</b>
                </div>
              )}

              {aiLastUsage && (
                <div className="text-xs text-muted-foreground" data-testid="claude-usage-summary">
                  Usage: entrada {aiLastUsage.input_tokens} tok · saída {aiLastUsage.output_tokens} tok · cache (write{" "}
                  {aiLastUsage.cache_creation_input_tokens} / read {aiLastUsage.cache_read_input_tokens}) · Custo estimado:{" "}
                  <b>${aiLastUsage.estimated_cost_usd.toFixed(4)}</b>
                </div>
              )}
            </section>

            {/* C.4 Item 4: Falha após 3 tentativas -> mostra erros, guarda rascunho e oferece "Tentar de novo" e "Importar mesmo assim" */}
            {aiDraftFailure && (
              <div
                role="alert"
                data-testid="claude-repair-failure"
                className="flex flex-col gap-2 rounded-lg border border-red-500/60 bg-red-950/50 p-3 text-xs text-red-100"
              >
                <strong className="text-red-300">
                  Não foi possível validar o motion após 3 tentativas de reparo automático:
                </strong>
                <ul className="list-disc pl-5 space-y-0.5">
                  {aiDraftFailure.errors.map((e, idx) => (
                    <li key={idx}>{e}</li>
                  ))}
                </ul>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    className="btn btn-accent btn-small"
                    onClick={() => void runClaudeGenerationLoop()}
                  >
                    Tentar de novo
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => {
                      importHtmlContent(aiDraftFailure.html, {
                        notes: aiDraftFailure.notes,
                        layerPreset: aiDraftFailure.layerPreset,
                      });
                      setAiDraftFailure(null);
                      setStudioTab("studio");
                    }}
                  >
                    Importar mesmo assim
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
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
                  Nenhum motion importado ainda. Arraste um arquivo <code>.html</code>, clique em &ldquo;+ Carregar Exemplo v1&rdquo; ou use a aba <b>✨ Gerar com Claude</b>.
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

            {/* A. MOTOR DE ÁUDIO PARA DJ (AGC, Trim, Antecipação, Medidores Contínuos, LEDs de Evento e BPM) */}
            <section className="flex flex-col gap-3 rounded-lg border border-border bg-secondary/30 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <strong className="text-xs uppercase tracking-wider text-muted-foreground">
                    6. Motor de Áudio para DJ (AGC + Fluxo Espectral + Grid BPM)
                  </strong>
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-bold ${
                      bpmLocked ? "bg-emerald-500/20 text-emerald-300" : "bg-secondary text-muted-foreground"
                    }`}
                    data-testid="dj-bpm-badge"
                  >
                    {audioFrame.bpm > 0 ? `${audioFrame.bpm} BPM` : "-- BPM"} · {bpmLocked ? "🔒 Travado" : "🔓 Destravado"}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <label className="btn btn-small cursor-pointer">
                    🎵 Arquivo
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
                    🔌 Linha
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
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => recalibrateAgc(beatStateRef.current)}
                    title="Zera o histórico do controle automático de ganho (AGC)"
                  >
                    Recalibrar AGC
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => realignDownbeatOnNextBeat(beatStateRef.current)}
                    title="Realinha o 1º tempo do compasso (downbeat) no próximo beat"
                  >
                    Realinhar compasso
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={handleTapTempo}
                    title="Atalho: tecla T"
                  >
                    Tap (T)
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={handleManualBeat}
                    title="Dispara beat + kick com força 1 (Atalho: tecla B)"
                  >
                    🥁 Pulso de Beat (B)
                  </button>
                </div>
              </div>

              {/* Controles de Ganho Trim (-12 a +12 dB) e Antecipação de Latência (0 a 150 ms) */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 text-xs">
                <label className="flex items-center gap-2">
                  <span className="w-36 text-muted-foreground">Trim de Ganho ({gainTrimDb} dB):</span>
                  <input
                    type="range"
                    aria-label="Trim de ganho (dB)"
                    min={-12}
                    max={12}
                    step={0.5}
                    value={gainTrimDb}
                    onChange={(e) => setGainTrimDb(Number(e.target.value))}
                    className="flex-1"
                  />
                </label>
                <label className="flex items-center gap-2">
                  <span className="w-44 text-muted-foreground">Antecipação ({anticipationMs} ms):</span>
                  <input
                    type="range"
                    aria-label="Antecipação (ms)"
                    min={0}
                    max={150}
                    step={5}
                    value={anticipationMs}
                    onChange={(e) => setAnticipationMs(Number(e.target.value))}
                    className="flex-1"
                  />
                </label>
              </div>

              {/* Barras ao vivo dos sinais contínuos + LEDs dos eventos (A.4) */}
              <div className="grid grid-cols-5 gap-2 text-xs" data-testid="central-audio-meters">
                {(
                  [
                    ["Bass", audioFrame.bass],
                    ["Mid", audioFrame.mid],
                    ["High", audioFrame.high],
                    ["Level", audioFrame.level],
                    ["Energy (4s)", audioFrame.energy],
                  ] as const
                ).map(([label, val]) => (
                  <div key={label} className="flex flex-col gap-1">
                    <div className="flex justify-between">
                      <span>{label}</span>
                      <b>{val.toFixed(2)}</b>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded bg-black/50">
                      <div className="h-full bg-purple-500 transition-all" style={{ width: `${Math.round(val * 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex flex-wrap items-center gap-2" data-testid="dj-event-leds">
                  {(
                    [
                      ["KICK", audioFrame.kick],
                      ["SNARE", audioFrame.snare],
                      ["HAT", audioFrame.hat],
                      ["BEAT", audioFrame.beat],
                      ["DOWNBEAT", audioFrame.downbeat],
                    ] as const
                  ).map(([name, val]) => (
                    <span
                      key={name}
                      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-bold ${
                        val > 0 ? "bg-purple-500 text-white" : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      ● {name}
                    </span>
                  ))}
                </div>
                <div className="text-muted-foreground">
                  beatPhase: <b>{audioFrame.beatPhase.toFixed(2)}</b> · barPhase: <b>{audioFrame.barPhase.toFixed(2)}</b> ·
                  Total beats: <span data-testid="central-beat-count">{beatCount}</span>
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

            {/* 3. EXECUÇÃO + 4. PAINEL AUTOMÁTICO + B. PAINEL DE REAÇÃO + 5. PRESETS + 8. CICLO DE VIDA */}
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
                        audioFrame={audioFrame}
                        isSelected={selectedSlotId === slot.slotId || slots.length === 1}
                        onSelectSlot={setSelectedSlotId}
                        onApplyReactToAll={applyReactToAllLayers}
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
        )}
      </DialogContent>
    </Dialog>
  );
}
