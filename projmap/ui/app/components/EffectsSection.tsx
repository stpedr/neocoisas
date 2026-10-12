"use client";

// Efeitos visuais importados do visual_frames (Adriel Vasques): Luz reativa,
// LEGO, Ecos em quadrinhos. A câmera vê as pessoas (YOLO na GPU) e a música do
// PC muda as cores. Aparecem nas superfícies com a fonte "Cena interativa".

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { EffectParams, EffectsCatalog, InteractState } from "../lib/types";

export default function EffectsSection({ st, onState, onError }: {
  st: InteractState | null;
  onState: (s: InteractState) => void;
  onError: (msg: string) => void;
}) {
  const [cat, setCat] = useState<EffectsCatalog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.effects().then(setCat).catch(() => setCat(null));
  }, []);
  if (!cat) return null;

  const active = st?.effect ?? null;
  const pick = async (name: string) => {
    setBusy(name);
    try {
      onState(await api.setEffect(name));
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao ligar o efeito");
    } finally {
      setBusy(null);
    }
  };
  const tune = async (changes: Partial<EffectParams>) => {
    try {
      onState(await api.effectParams(changes));
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Falha ao ajustar");
    }
  };
  const p = st?.effect_params;

  return (
    <div className="effects-section">
      <div className="card-head">
        <h3>Efeitos visuais <span className="dim small">(visual_frames)</span></h3>
        {active && <button className="btn btn-small" onClick={() => pick("off")}>Voltar à cena</button>}
      </div>
      {!cat.imported && (
        <p className="dim small">
          Ainda não importados. No terminal do ProjMap: <code>python -m projmap.effects.importar</code> (aponte para a pasta do
          visual_frames clonado).
        </p>
      )}
      <div className="preset-grid">
        {Object.entries(cat.effects).map(([key, e]) => (
          <button key={key} className={`btn btn-small ${active === key ? "btn-accent" : ""}`} title={e.description}
                  disabled={!e.available || busy !== null} onClick={() => pick(key)}>
            {busy === key ? "Ligando…" : e.title}
          </button>
        ))}
      </div>
      {active && (
        <>
          <p className="dim small">
            {st?.effect_status ? `⚠ ${st.effect_status}` : "Câmera e música ativas. Use a fonte “Cena interativa” numa superfície."}
          </p>
          {p && (
            <div className="color-controls">
              <label className="slider">
                <span className="color-row">Brilho <span className="dim">{Math.round(p.brilho * 100)}%</span></span>
                <input type="range" min={0.3} max={1.6} step={0.05} value={p.brilho} onChange={(e) => tune({ brilho: Number(e.target.value) })} />
              </label>
              <label className="slider">
                <span className="color-row">Sensibilidade ao som <span className="dim">{p.sensibilidade_som.toFixed(1)}×</span></span>
                <input type="range" min={0.2} max={3} step={0.1} value={p.sensibilidade_som} onChange={(e) => tune({ sensibilidade_som: Number(e.target.value) })} />
              </label>
              {active === "vf-luz" && (
                <>
                  <label className="toggle"><input type="checkbox" checked={p.orbes_maos} onChange={(e) => tune({ orbes_maos: e.target.checked })} /> Orbes nas mãos</label>
                  <label className="toggle"><input type="checkbox" checked={p.cor_segue_musica} onChange={(e) => tune({ cor_segue_musica: e.target.checked })} /> Cor segue a música</label>
                  {!p.cor_segue_musica && (
                    <label className="slider">
                      <span className="color-row">Cor fixa</span>
                      <input type="range" min={0} max={1} step={0.01} value={p.matiz_fixo} onChange={(e) => tune({ matiz_fixo: Number(e.target.value) })} />
                    </label>
                  )}
                </>
              )}
              {active === "vf-lego" && (
                <>
                  <label className="slider">
                    <span className="color-row">Tamanho da peça <span className="dim">{Math.round(p.tamanho_peca)}</span></span>
                    <input type="range" min={10} max={28} step={1} value={p.tamanho_peca} onChange={(e) => tune({ tamanho_peca: Number(e.target.value) })} />
                  </label>
                  <label className="toggle"><input type="checkbox" checked={p.lego_cair} onChange={(e) => tune({ lego_cair: e.target.checked })} /> Peças caem quando a pessoa se mexe</label>
                </>
              )}
              {active === "vf-ecos" && (
                <>
                  <label className="slider">
                    <span className="color-row">Quantidade de ecos <span className="dim">{Math.round(p.quantidade_ecos)}</span></span>
                    <input type="range" min={1} max={8} step={1} value={p.quantidade_ecos} onChange={(e) => tune({ quantidade_ecos: Number(e.target.value) })} />
                  </label>
                  <label className="slider">
                    <span className="color-row">Distância entre ecos <span className="dim">{Math.round(p.distancia_ecos)}</span></span>
                    <input type="range" min={1} max={8} step={1} value={p.distancia_ecos} onChange={(e) => tune({ distancia_ecos: Number(e.target.value) })} />
                  </label>
                </>
              )}
            </div>
          )}
        </>
      )}
      <p className="dim small">Efeitos de Adriel Vasques (visual_frames), usados com permissão.</p>
    </div>
  );
}
