"use client";

// Widget "Celular": controle remoto pela Wi-Fi (QR) e, com a interação ligada,
// o celular como sensor pelo cabo USB. O mestre só mostra token/QR a quem está
// na própria máquina (/api/remote/pair).

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useEscape } from "../lib/interact";
import type { InteractState } from "../lib/types";

type Pair = Awaited<ReturnType<typeof api.pairInfo>>;

export default function PhoneDialog({ open, onClose, interact }: {
  open: boolean;
  onClose: () => void;
  interact: InteractState | null; // null = interação desligada
}) {
  const [pair, setPair] = useState<Pair | null>(null);
  const [failed, setFailed] = useState(false);
  useEscape(open, onClose);

  useEffect(() => {
    if (!open) return;
    api.pairInfo().then(setPair).catch(() => setFailed(true)); // aberto de outra máquina
  }, [open]);
  if (!open) return null;

  return (
    <div className="gallery-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label="Celular" onClick={(e) => e.stopPropagation()}>
        <div className="gallery-head">
          <h2>📱 Celular</h2>
          <button className="btn btn-small" onClick={onClose}>Fechar</button>
        </div>

        <h3>Controle remoto (Wi-Fi)</h3>
        {failed && <p className="dim small">O QR só aparece no computador do mestre.</p>}
        {pair && !pair.lan && (
          <>
            <p className="dim small">
              O mestre está só nesta máquina. Para o celular alcançar, abra pelo lançador com <b>Controlar o show pelo
              celular</b> marcado (ou rode com <code>--host 0.0.0.0</code>), na mesma rede Wi-Fi.
            </p>
            <a className="btn btn-small" href="/remote/" target="_blank" rel="noreferrer">Abrir o remote aqui</a>
          </>
        )}
        {pair?.lan && (
          <div className="phone-pair">
            {pair.qr_svg ? (
              <div className="qr">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  width={222}
                  height={222}
                  src={`data:image/svg+xml;utf8,${encodeURIComponent(
                    pair.qr_svg.includes("xmlns=")
                      ? pair.qr_svg
                      : pair.qr_svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" '),
                  )}`}
                  alt="QR Code de pareamento"
                />
              </div>
            ) : (
              <p className="dim small">Instale <code>segno</code> no mestre para ver o QR.</p>
            )}
            <div>
              <p className="small">Aponte a câmera do celular para o QR. Ou abra:</p>
              <a className="small remote-link" href={pair.url} target="_blank" rel="noreferrer">{pair.url}</a>
              <p className="dim small">O token muda a cada execução (ou fixe com <code>--token</code>).</p>
            </div>
          </div>
        )}

        {interact && (
          <>
            <h3>Celular como sensor (cabo USB)</h3>
            {interact.sensor === "phone" ? (
              <p className="small">
                {interact.phone?.connected
                  ? `✓ Celular conectado (${Math.round(interact.phone.fps)} fps).`
                  : "Aguardando o celular. Ligue a Depuração USB, conecte o cabo e toque em “Iniciar sensor” na página que abrir nele."}
              </p>
            ) : (
              <p className="dim small">
                O sensor atual é <b>{interact.sensor === "sim" ? "simulação" : interact.sensor}</b>. Para usar a câmera do celular,
                marque <b>Celular ligado no cabo USB</b> na seção Interação do lançador (ou rode com <code>--sensor phone --adb</code>).
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
