// Lançador do app: descobre o mestre (QR ou digitado), confere se responde e
// navega a WebView para o /remote/ servido pelo próprio mestre. Assim o app
// sempre usa a UI da mesma versão do mestre. O token vai no hash (#t=), que a
// página do remote guarda no localStorage dela.
"use strict";

const STORE = "projmap.masters";

// Só IPs de rede local: o app libera HTTP sem TLS, então não navega para a internet.
function isPrivateHost(host) {
  if (host === "localhost" || host === "127.0.0.1") return true;
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return false;
  if (m.slice(1).some((x) => Number(x) > 255)) return false;
  const a = Number(m[1]);
  const b = Number(m[2]);
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

// Aceita a URL do QR (http://ip:porta/remote/#t=tok) ou "ip[:porta]".
function parseTarget(text, fallbackToken) {
  let raw = String(text || "").trim();
  if (!raw) throw new Error("Informe o IP do mestre.");
  if (!/^https?:\/\//i.test(raw)) raw = "http://" + raw;
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("Endereço inválido.");
  }
  if (!isPrivateHost(url.hostname)) {
    throw new Error("Use um IP da rede local (192.168.x.x, 10.x.x.x ou 172.16–31.x.x).");
  }
  const m = /[#&]t=([^&]+)/.exec(url.hash);
  return {
    host: url.hostname,
    port: Number(url.port) || 8100,
    token: m ? decodeURIComponent(m[1]) : fallbackToken || "",
  };
}

function remoteUrl(t) {
  return `http://${t.host}:${t.port}/remote/` + (t.token ? `#t=${encodeURIComponent(t.token)}` : "");
}

if (typeof module !== "undefined") {
  // Testes (node): só as funções puras.
  module.exports = { isPrivateHost, parseTarget, remoteUrl };
} else {
  startLauncher();
}

function startLauncher() {
  const $ = (id) => document.getElementById(id);
  let cancelled = false;

  function loadMasters() {
    try {
      return JSON.parse(localStorage.getItem(STORE) || "[]");
    } catch {
      return [];
    }
  }

  function saveMaster(t) {
    const list = loadMasters().filter((m) => !(m.host === t.host && m.port === t.port));
    list.unshift({ host: t.host, port: t.port, token: t.token, at: Date.now() });
    try {
      localStorage.setItem(STORE, JSON.stringify(list.slice(0, 5)));
    } catch {
      /* sem armazenamento: só não lembra */
    }
  }

  function say(text, kind) {
    const el = $("msg");
    el.textContent = text;
    el.className = "msg " + (kind || "");
  }

  // Testa se o mestre responde. /remote/ é estático e público (o token só vale
  // para /api), e "no-cors" basta: só interessa se a rede alcança.
  async function reachable(t, ms = 3000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
      await fetch(`http://${t.host}:${t.port}/remote/`, { mode: "no-cors", signal: ctrl.signal, cache: "no-store" });
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  async function go(t) {
    say(`Procurando ${t.host}:${t.port}…`);
    if (!(await reachable(t))) {
      say(`O mestre ${t.host}:${t.port} não respondeu. Ele está rodando com --host 0.0.0.0 e o celular na mesma Wi-Fi?`, "err");
      return false;
    }
    if (cancelled) return false;
    saveMaster(t);
    say("Conectado. Abrindo o remote…", "ok");
    window.location.href = remoteUrl(t);
    return true;
  }

  // QR por foto: decodifica localmente (jsQR), sem rede nem plugin nativo.
  async function decodeQr(file) {
    const bmp = await createImageBitmap(file);
    // Fotos de 12 MP são lentas para o jsQR; 1200 px no lado maior bastam.
    const scale = Math.min(1, 1200 / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = window.jsQR(img.data, img.width, img.height, { inversionAttempts: "attemptBoth" });
    return code ? code.data : null;
  }

  $("qr-file").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    say("Lendo o QR…");
    try {
      const text = await decodeQr(file);
      if (!text) return say("Não achei um QR na foto. Chegue mais perto e tente de novo.", "err");
      const t = parseTarget(text);
      $("host").value = t.host;
      $("port").value = t.port;
      $("token").value = t.token;
      cancelled = false;
      await go(t);
    } catch (err) {
      say(err.message || "Falha ao ler o QR.", "err");
    }
  });

  $("connect").addEventListener("click", async () => {
    try {
      const port = $("port").value.trim();
      const t = parseTarget($("host").value + (port ? ":" + port : ""), $("token").value.trim());
      cancelled = false;
      await go(t);
    } catch (err) {
      say(err.message, "err");
    }
  });

  $("auto-cancel").addEventListener("click", () => {
    cancelled = true;
    $("auto").hidden = true;
    say("");
  });

  function renderRecent() {
    const list = loadMasters();
    $("recent-card").hidden = list.length === 0;
    const box = $("recent");
    box.textContent = "";
    for (const m of list) {
      const b = document.createElement("button");
      b.className = "btn";
      const label = document.createElement("span");
      label.textContent = `${m.host}:${m.port}`;
      const hint = document.createElement("small");
      hint.textContent = "conectar ›";
      b.append(label, hint);
      b.addEventListener("click", () => {
        cancelled = false;
        go(m);
      });
      box.appendChild(b);
    }
  }

  // Abertura: reconecta sozinho ao último mestre, a menos que o usuário tenha
  // voltado de propósito pelo "Trocar mestre" do remote (?pick=1).
  (async function start() {
    renderRecent();
    const last = loadMasters()[0];
    const picking = new URLSearchParams(location.search).has("pick");
    if (!last || picking) return;
    $("auto-host").textContent = `${last.host}:${last.port}`;
    $("auto").hidden = false;
    const ok = await go(last);
    if (!ok) $("auto").hidden = true;
  })();
}
