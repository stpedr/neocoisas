"use client";

// Presets de imagem: os prontos (Ambiente claro, Cores vivas…) e os SEUS,
// salvos no mestre (valem para todos os shows desta máquina). Um clique aplica
// no alvo (a superfície selecionada ou o projetor inteiro).

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { ColorAdjust, ColorPreset } from "../lib/types";
import { PRESETS } from "./ColorControls";

const CHANGED = "projmap:color-presets";

function same(a: ColorAdjust, b: ColorAdjust) {
  return (Object.keys(a) as (keyof ColorAdjust)[]).every((k) => Math.abs(a[k] - b[k]) < 1e-6);
}

export default function ColorPresets({ value, onApply, onError, target }: {
  value: ColorAdjust;
  onApply: (c: ColorAdjust) => void;
  onError: (m: string) => void;
  target: string; // "a superfície" / "o projetor": só para os textos
}) {
  const [mine, setMine] = useState<ColorPreset[]>([]);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    const load = () => api.colorPresets().then((r) => setMine(r.presets)).catch(() => {});
    load();
    window.addEventListener(CHANGED, load);
    return () => window.removeEventListener(CHANGED, load);
  }, []);

  const save = async () => {
    if (!name.trim()) return;
    try {
      const r = await api.saveColorPreset(name.trim(), value);
      setMine(r.presets);
      setNaming(false);
      setName("");
      window.dispatchEvent(new Event(CHANGED));
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao salvar o preset");
    }
  };

  const remove = async (p: ColorPreset) => {
    if (!confirm(`Apagar o preset "${p.name}"?`)) return;
    try {
      const r = await api.deleteColorPreset(p.id);
      setMine(r.presets);
      window.dispatchEvent(new Event(CHANGED));
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao apagar o preset");
    }
  };

  return (
    <div className="presets">
      <div className="preset-grid">
        {PRESETS.map((p) => (
          <button key={p.name} className={`btn btn-small ${same(p.color, value) ? "btn-accent" : ""}`} title={p.hint}
                  onClick={() => onApply({ ...p.color })}>
            {p.name}
          </button>
        ))}
      </div>
      {mine.length > 0 && (
        <>
          <span className="dim small">Meus presets</span>
          <div className="preset-grid">
            {mine.map((p) => (
              <span key={p.id} className={`chip ${same(p.color, value) ? "chip-on" : ""}`}>
                <button className="chip-main" title={`Aplicar em ${target}`} onClick={() => onApply({ ...p.color })}>⭐ {p.name}</button>
                <button className="chip-x" aria-label={`Apagar ${p.name}`} title="Apagar preset" onClick={() => remove(p)}>×</button>
              </span>
            ))}
          </div>
        </>
      )}
      {naming ? (
        <div className="row">
          <input autoFocus value={name} maxLength={60} placeholder="Nome (ex.: Parede da igreja)" onChange={(e) => setName(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") void save(); if (e.key === "Escape") setNaming(false); }} />
          <button className="btn btn-small btn-accent" disabled={!name.trim()} onClick={save}>Salvar</button>
          <button className="btn btn-small" onClick={() => setNaming(false)}>Cancelar</button>
        </div>
      ) : (
        <button className="btn btn-small" onClick={() => setNaming(true)} title="Guarda os ajustes atuais com um nome para reaplicar depois">
          ＋ Salvar ajuste atual como preset
        </button>
      )}
    </div>
  );
}
