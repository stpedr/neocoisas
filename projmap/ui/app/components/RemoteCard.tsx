"use client";

// Card "Remote" do editor (F6): QR para abrir o controle no celular.
// O mestre só mostra token/QR a quem está na própria máquina (/api/remote/pair).

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Pair = Awaited<ReturnType<typeof api.pairInfo>>;

export default function RemoteCard() {
  const [pair, setPair] = useState<Pair | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.pairInfo().then(setPair).catch(() => setPair(null)); // aberto de outra máquina: sem card
  }, []);
  if (!pair) return null;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Remote no celular</h2>
        <button className="btn btn-small" onClick={() => setOpen(!open)}>{open ? "Ocultar" : "Mostrar QR"}</button>
      </div>
      {!pair.lan && (
        <p className="dim small">
          O mestre está só nesta máquina. Para o celular alcançar, reinicie com <code>--host 0.0.0.0</code> (mesma rede Wi-Fi).
        </p>
      )}
      {open && pair.lan && (
        <>
          {pair.qr_svg ? (
            <div className="qr" dangerouslySetInnerHTML={{ __html: pair.qr_svg }} />
          ) : (
            <p className="dim small">Instale <code>segno</code> no mestre para ver o QR.</p>
          )}
          <a className="small remote-link" href={pair.url} target="_blank" rel="noreferrer">{pair.url}</a>
          <p className="dim small">Token: <code>{pair.token}</code> · muda a cada execução (ou fixe com <code>--token</code>).</p>
        </>
      )}
      {open && !pair.lan && (
        <a className="btn btn-small" href="/remote/" target="_blank" rel="noreferrer">Abrir remote aqui</a>
      )}
    </section>
  );
}
