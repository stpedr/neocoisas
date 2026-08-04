"use client";

import { useCallback, useEffect, useState } from "react";
import { api, AvailableModels, ModelsPayload } from "../lib/api";

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
  const [error, setError] = useState("");
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

  if (!models) return <p className="muted">{error || "Carregando modelos…"}</p>;

  return (
    <div>
      {error && <div className="alert error">{error}</div>}
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
    </div>
  );
}
