"use client";

import { useCallback, useEffect, useState } from "react";
import { api, AvailableModels, ModelsPayload } from "../lib/api";
import { useToast } from "./Toast";

const CAP_LABEL: Record<string, string> = {
  text: "Texto (LLM)",
  image: "Imagem",
  voice: "Voz",
  video: "Vídeo",
  publisher: "Publicação",
};

export default function ModelsView() {
  const [models, setModels] = useState<ModelsPayload | null>(null);
  const [available, setAvailable] = useState<AvailableModels>({});
  const toast = useToast();
  const setError = (m: string) => toast(m, "error");
  const [saving, setSaving] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, a] = await Promise.all([api.getModels(), api.getAvailableModels()]);
      setModels(m);
      setAvailable(a);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function change(capability: string, provider: string, model?: string | null) {
    setSaving(capability);
    setError("");
    try {
      setModels(await api.selectModel({ capability, provider, model }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving("");
    }
  }

  async function changeAgent(agent: string, model: string | null) {
    setSaving("agent:" + agent);
    setError("");
    try {
      setModels(await api.selectAgentModel({ agent, model }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving("");
    }
  }

  const AGENT_LABEL: Record<string, string> = {
    idea: "Ideias", script: "Roteirista", critic: "Crítico", editor: "Editor",
    titler: "Títulos", translator: "Tradutor", analyst: "Analista", niche: "Nicho",
  };

  if (!models) return <p className="muted">Carregando modelos…</p>;

  return (
    <div>
      <p className="muted" style={{ marginBottom: 16 }}>
        Escolha o provedor e o modelo de cada capacidade. A troca vale na hora e é
        persistida. Chaves ausentes aparecem sinalizadas.
      </p>

      {Object.entries(models.capabilities).map(([cap, info]) => {
        const modelList = available[cap]?.[info.current.provider] ||
          info.models[info.current.provider] || [];
        return (
          <div className="panel" key={cap} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{CAP_LABEL[cap] || cap}</strong>
              {saving === cap && <span className="spinner" />}
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <div className="field">
                <label>Provedor</label>
                <select
                  className="select"
                  value={info.current.provider}
                  onChange={(e) => change(cap, e.target.value)}
                >
                  {info.providers.map((p) => {
                    const req = info.requires[p] || [];
                    const ok = info.configured[p];
                    const falta = req.length && !ok ? " ⚠ chave" : "";
                    return (
                      <option key={p} value={p}>
                        {p}
                        {falta}
                      </option>
                    );
                  })}
                </select>
                {(info.requires[info.current.provider]?.length || 0) > 0 &&
                  !info.configured[info.current.provider] && (
                    <span className="hint">
                      Requer: {info.requires[info.current.provider].join(", ")} (no .env)
                    </span>
                  )}
              </div>
              {modelList.length > 0 && (
                <div className="field">
                  <label>Modelo</label>
                  <select
                    className="select"
                    value={info.current.model || ""}
                    onChange={(e) => change(cap, info.current.provider, e.target.value)}
                  >
                    {modelList.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>
        );
      })}

      <div className="section-title">Override de modelo por agente</div>
      <p className="muted" style={{ marginBottom: 10 }}>
        Deixe um agente com modelo próprio (ex.: crítico mais forte). “(global)”
        usa o modelo de texto padrão.
      </p>
      {(() => {
        const textProvider = models.capabilities.text.current.provider;
        const textModels =
          available["text"]?.[textProvider] ||
          models.capabilities.text.models[textProvider] ||
          [];
        return (
          <div className="panel">
            {Object.entries(models.agents).map(([agent, info]) => (
              <div className="row" key={agent} style={{ alignItems: "center" }}>
                <div style={{ flex: 1, minWidth: 120 }}>
                  <strong>{AGENT_LABEL[agent] || agent}</strong>
                  {info.override && <span className="chip" style={{ marginLeft: 8 }}>override</span>}
                </div>
                <div className="field" style={{ flex: 1 }}>
                  <select
                    className="select"
                    value={info.override ? info.model || "" : ""}
                    onChange={(e) => changeAgent(agent, e.target.value || null)}
                  >
                    <option value="">(global)</option>
                    {textModels.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                {saving === "agent:" + agent && <span className="spinner" />}
              </div>
            ))}
          </div>
        );
      })()}
    </div>
  );
}
