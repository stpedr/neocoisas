"use client";

// Efeitos visuais importados do visual_frames (Adriel Vasques): Luz reativa,
// LEGO, Ecos em quadrinhos, Bichinho espelho e Salto de paraquedas. A câmera vê
// as pessoas (YOLO na GPU) e a música do PC muda as cores. Aparecem nas
// superfícies com a fonte "Cena interativa".

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { EffectParams, EffectsCatalog, InteractState } from "../lib/types";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Slider } from "./ui/slider";

function Field({ label, display, value, onValueChange, ...range }: {
  label: string;
  display?: string;
  value: number;
  onValueChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      <span className="flex justify-between gap-2">
        {label} {display && <span>{display}</span>}
      </span>
      <Slider {...range} value={[value]} onValueChange={([v]) => onValueChange(v)} aria-label={label} />
    </label>
  );
}

function Toggle({ label, checked, onCheckedChange }: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-foreground">
      <Checkbox checked={checked} onCheckedChange={(v) => onCheckedChange(v === true)} aria-label={label} />
      {label}
    </label>
  );
}

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
    <div className="flex flex-col gap-2 rounded-radius-sm border border-border p-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="m-0 text-[13px] font-semibold">Efeitos visuais <span className="font-normal text-muted-foreground">(visual_frames)</span></h3>
        {active && (
          <Button variant="default" size="sm" onClick={() => pick("off")}>
            Voltar à cena
          </Button>
        )}
      </div>
      {!cat.imported && (
        <p className="m-0 text-xs text-muted-foreground">
          Ainda não importados. No terminal do ProjMap: <code>python -m projmap.effects.importar</code> (aponte para a pasta do
          visual_frames clonado).
        </p>
      )}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-1.5">
        {Object.entries(cat.effects).map(([key, e]) => (
          <Button
            key={key}
            variant={active === key ? "primary" : "default"}
            size="sm"
            title={e.description}
            disabled={!e.available || busy !== null}
            onClick={() => pick(key)}
          >
            {busy === key ? "Ligando…" : e.title}
          </Button>
        ))}
      </div>
      {active && (
        <>
          <p className="m-0 text-xs text-muted-foreground">
            {st?.effect_status ? `⚠ ${st.effect_status}` : "Câmera e música ativas. Use a fonte “Cena interativa” numa superfície."}
          </p>
          {p && (
            <div className="flex flex-col gap-1.5">
              <Field label="Brilho" display={`${Math.round(p.brilho * 100)}%`} min={0.3} max={1.6} step={0.05}
                     value={p.brilho} onValueChange={(v) => tune({ brilho: v })} />
              <Field label="Sensibilidade ao som" display={`${p.sensibilidade_som.toFixed(1)}×`} min={0.2} max={3} step={0.1}
                     value={p.sensibilidade_som} onValueChange={(v) => tune({ sensibilidade_som: v })} />
              {active === "vf-luz" && (
                <>
                  <Toggle label="Orbes nas mãos" checked={p.orbes_maos} onCheckedChange={(v) => tune({ orbes_maos: v })} />
                  <Toggle label="Cor segue a música" checked={p.cor_segue_musica} onCheckedChange={(v) => tune({ cor_segue_musica: v })} />
                  {!p.cor_segue_musica && (
                    <Field label="Cor fixa" min={0} max={1} step={0.01} value={p.matiz_fixo} onValueChange={(v) => tune({ matiz_fixo: v })} />
                  )}
                </>
              )}
              {active === "vf-lego" && (
                <>
                  <Field label="Tamanho da peça" display={`${Math.round(p.tamanho_peca)}`} min={10} max={28} step={1}
                         value={p.tamanho_peca} onValueChange={(v) => tune({ tamanho_peca: v })} />
                  <Toggle label="Peças caem quando a pessoa se mexe" checked={p.lego_cair} onCheckedChange={(v) => tune({ lego_cair: v })} />
                </>
              )}
              {active === "vf-ecos" && (
                <>
                  <Field label="Quantidade de ecos" display={`${Math.round(p.quantidade_ecos)}`} min={1} max={8} step={1}
                         value={p.quantidade_ecos} onValueChange={(v) => tune({ quantidade_ecos: v })} />
                  <Field label="Distância entre ecos" display={`${Math.round(p.distancia_ecos)}`} min={1} max={8} step={1}
                         value={p.distancia_ecos} onValueChange={(v) => tune({ distancia_ecos: v })} />
                </>
              )}
              {active === "vf-bichinho" && (
                <>
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-1.5">
                    {["Gato", "Dinossauro", "Coelho"].map((nome, i) => (
                      <Button key={nome} variant={Math.round(p.animal) === i ? "primary" : "default"} size="sm"
                              onClick={() => tune({ animal: i })}>
                        {nome}
                      </Button>
                    ))}
                  </div>
                  <Toggle label="Fundo colorido" checked={p.fundo_colorido} onCheckedChange={(v) => tune({ fundo_colorido: v })} />
                </>
              )}
              {active === "vf-paraquedas" && (
                <Field label="Intervalo do avião" display={`${Math.round(p.intervalo_aviao)}s`} min={3} max={20} step={1}
                       value={p.intervalo_aviao} onValueChange={(v) => tune({ intervalo_aviao: v })} />
              )}
            </div>
          )}
        </>
      )}
      <p className="m-0 text-xs text-muted-foreground">Efeitos de Adriel Vasques (visual_frames), usados com permissão.</p>
    </div>
  );
}
