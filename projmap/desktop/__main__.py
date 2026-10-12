"""Lançador do ProjMap (janela tkinter): é o que o atalho do Menu Iniciar abre.

Escolhe o show (ou cria um novo), onde sai a imagem e se o celular pode
conectar; ao clicar "Abrir", inicia o mestre em segundo plano, mostra o link do
celular e abre o editor no navegador. Fechar a janela encerra o mestre.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from .core import (REPO_ROOT, Settings, list_shows, load_settings, master_command, remote_url_from_log,
                   safe_show_name, save_settings, ui_built)

BG = "#0b0f17"
CARD = "#141a24"
FG = "#e8eef6"
DIM = "#94a3b8"
ACCENT = "#7c5cff"
NEW = "＋ Novo show…"
SENSORS = ["Pessoa simulada (sem câmera)", "Webcam (ex.: Logitech C920)", "Celular como sensor (/sensor)"]


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ProjMap")
        self.configure(bg=BG)
        self.minsize(460, 0)
        self.s: Settings = load_settings()
        self.proc: subprocess.Popen | None = None
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.remote_url = ""
        icon = REPO_ROOT / "projmap" / "desktop" / "projmap.ico"
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass
        self._style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.after(200, self._pump)

    # ------------------------------------------------------------------ UI
    def _style(self) -> None:
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=CARD, font=("Segoe UI", 10))
        st.configure("Card.TFrame", background=CARD)
        st.configure("Card.TLabel", background=CARD, foreground=FG)
        st.configure("Dim.TLabel", background=CARD, foreground=DIM, font=("Segoe UI", 9))
        st.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI Semibold", 16))
        st.configure("TRadiobutton", background=CARD, foreground=FG)
        st.configure("TCheckbutton", background=CARD, foreground=FG)
        st.map("TRadiobutton", background=[("active", CARD)])
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#fff", font=("Segoe UI Semibold", 11), padding=8)
        st.map("Accent.TButton", background=[("active", "#6a4cf0"), ("disabled", "#3b3466")])
        st.configure("TButton", padding=6, background="#1b2330", foreground=FG, bordercolor="#33415a")
        st.map("TButton", background=[("active", "#263041"), ("disabled", CARD)], foreground=[("disabled", "#5b6b82")])
        # Caixa de seleção do show legível no tema escuro (o "readonly" do clam é claro).
        st.configure("TCombobox", fieldbackground="#1b2330", background="#1b2330", foreground=FG, arrowcolor=FG,
                     bordercolor="#33415a", padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", "#1b2330")], foreground=[("readonly", FG)],
               selectbackground=[("readonly", "#1b2330")], selectforeground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        st.configure("TSpinbox", fieldbackground="#1b2330", foreground=FG, arrowcolor=FG, bordercolor="#33415a")
        for w in ("TRadiobutton", "TCheckbutton"):
            st.configure(w, indicatorbackground="#1b2330", indicatorforeground=ACCENT, indicatormargin=4)
            st.map(w, indicatorbackground=[("selected", "#1b2330")], indicatorforeground=[("selected", ACCENT)])

    def _card(self, title: str) -> ttk.Frame:
        f = ttk.Frame(self, style="Card.TFrame", padding=12)
        f.pack(fill="x", padx=14, pady=(0, 10))
        ttk.Label(f, text=title, style="Card.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        return f

    def _build(self) -> None:
        ttk.Label(self, text="◆ ProjMap", style="Title.TLabel").pack(anchor="w", padx=14, pady=(14, 10))

        # Show
        c = self._card("Show")
        row = ttk.Frame(c, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.show_var = tk.StringVar()
        self.show_box = ttk.Combobox(row, textvariable=self.show_var, state="readonly")
        self.show_box.pack(side="left", fill="x", expand=True)
        self.show_box.bind("<<ComboboxSelected>>", self._on_show)
        ttk.Button(row, text="Pasta…", command=self._pick_dir).pack(side="left", padx=(6, 0))
        self.dir_lbl = ttk.Label(c, style="Dim.TLabel")
        self.dir_lbl.pack(anchor="w", pady=(4, 0))
        self._refresh_shows()

        # Saída
        c = self._card("Onde sai a imagem")
        self.out_var = tk.StringVar(value=self.s.output)
        r = ttk.Frame(c, style="Card.TFrame")
        r.pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(r, text="Projetor (tela cheia no monitor", value="display", variable=self.out_var).pack(side="left")
        self.disp_var = tk.IntVar(value=self.s.display)
        ttk.Spinbox(r, from_=0, to=8, width=3, textvariable=self.disp_var).pack(side="left")
        ttk.Label(r, text=")", style="Card.TLabel").pack(side="left")
        ttk.Radiobutton(c, text="Janela de teste (sem projetor)", value="window", variable=self.out_var).pack(anchor="w")
        ttk.Radiobutton(c, text="Só o editor (sem saída)", value="none", variable=self.out_var).pack(anchor="w")
        ttk.Label(c, text="Monitor 0 é a tela principal; o projetor costuma ser o 1.", style="Dim.TLabel").pack(anchor="w")

        # Interação
        c = self._card("Interação (jogos com fantasmas, estrela…)")
        r = ttk.Frame(c, style="Card.TFrame")
        r.pack(fill="x", pady=(6, 0))
        self.sensor_var = tk.StringVar(value={"sim": SENSORS[0], "webcam": SENSORS[1], "phone": SENSORS[2]}.get(self.s.sensor, SENSORS[0]))
        ttk.Combobox(r, textvariable=self.sensor_var, values=SENSORS, state="readonly", width=34).pack(side="left")
        r2 = ttk.Frame(c, style="Card.TFrame")
        r2.pack(fill="x", pady=(6, 0))
        ttk.Label(r2, text="Câmera:", style="Card.TLabel").pack(side="left")
        self.camera_var = tk.StringVar(value=self.s.camera)
        self.camera_box = ttk.Combobox(r2, textvariable=self.camera_var, state="readonly", width=30)
        self.camera_box.pack(side="left", padx=(6, 0))
        ttk.Button(r2, text="↻", width=3, command=self._load_cameras).pack(side="left", padx=(6, 0))
        ttk.Label(c, text="Webcam: conecte a Logitech C920 antes de abrir; 'auto' a escolhe sozinho.", style="Dim.TLabel").pack(anchor="w")
        self.after(300, self._load_cameras)

        # Celular
        c = self._card("Celular")
        self.lan_var = tk.BooleanVar(value=self.s.lan)
        ttk.Checkbutton(c, text="Permitir controlar pelo celular (mesma rede Wi-Fi)", variable=self.lan_var).pack(anchor="w", pady=(6, 0))
        self.browser_var = tk.BooleanVar(value=self.s.open_browser)
        ttk.Checkbutton(c, text="Abrir o editor no navegador", variable=self.browser_var).pack(anchor="w")

        # Ações
        self.btn = ttk.Button(self, text="Abrir", style="Accent.TButton", command=self._toggle)
        self.btn.pack(fill="x", padx=14)
        r = ttk.Frame(self)
        r.pack(fill="x", padx=14, pady=(8, 0))
        self.edit_btn = ttk.Button(r, text="Abrir editor", command=self._open_editor, state="disabled")
        self.edit_btn.pack(side="left")
        self.phone_btn = ttk.Button(r, text="Copiar link do celular", command=self._copy_remote, state="disabled")
        self.phone_btn.pack(side="left", padx=6)
        self.status = tk.StringVar(value="Parado.")
        ttk.Label(self, textvariable=self.status, foreground=DIM, wraplength=430, justify="left").pack(anchor="w", padx=14, pady=(8, 4))

        if not ui_built():
            self.status.set("A interface ainda não foi compilada. Rode uma vez: cd projmap/ui && npm ci && npm run build")

        log_f = ttk.Frame(self, padding=(14, 0, 14, 14))
        log_f.pack(fill="both", expand=True)
        self.log = tk.Text(log_f, height=7, bg=CARD, fg=DIM, insertbackground=FG, relief="flat", font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ câmeras
    def _load_cameras(self) -> None:
        def work():
            try:
                from ..interact.cameras import choose_camera, list_cameras

                cams = list_cameras()
                pick = choose_camera(cams, "auto")
            except Exception:  # noqa: BLE001 — sem OpenCV/ffmpeg: fica só "auto"
                cams, pick = [], None
            self.after(0, lambda: self._set_cameras(cams, pick))

        threading.Thread(target=work, daemon=True).start()

    def _set_cameras(self, cams, pick) -> None:
        auto = f"auto ({pick.name})" if pick else "auto"
        self._cams = {auto: "auto", **{f"{c.index}: {c.name}" + (" (virtual)" if c.virtual else ""): str(c.index) for c in cams}}
        self.camera_box["values"] = list(self._cams)
        current = self.s.camera or "auto"
        label = next((k for k, v in self._cams.items() if v == current), auto)
        self.camera_var.set(label)

    def _camera_value(self) -> str:
        return getattr(self, "_cams", {}).get(self.camera_var.get(), self.camera_var.get() or "auto")

    # ------------------------------------------------------------ shows
    def _refresh_shows(self, select: str | None = None) -> None:
        shows = list_shows(self.s.shows_dir)
        self.show_box["values"] = shows + [NEW]
        want = select or self.s.last_show
        self.show_var.set(want if want in shows else (shows[0] if shows else NEW))
        self.dir_lbl.configure(text=f"Pasta dos shows: {self.s.shows_dir}")

    def _on_show(self, _e=None) -> None:
        if self.show_var.get() != NEW:
            return
        name = _ask(self, "Novo show", "Nome do show (ex.: Natal na fachada):")
        if not name:
            self._refresh_shows()
            return
        name = safe_show_name(name)
        self.show_box["values"] = [*self.show_box["values"][:-1], name, NEW]
        self.show_var.set(name)

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.s.shows_dir, title="Pasta onde ficam os shows")
        if d:
            self.s.shows_dir = d
            self._refresh_shows()

    # ------------------------------------------------------------- mestre
    def _toggle(self) -> None:
        if self.proc and self.proc.poll() is None:
            self._stop()
            return
        show = self.show_var.get()
        if not show or show == NEW:
            messagebox.showinfo("ProjMap", "Escolha um show ou crie um novo.")
            return
        s = self.s
        s.last_show, s.output, s.display = show, self.out_var.get(), int(self.disp_var.get() or 0)
        s.lan, s.open_browser = bool(self.lan_var.get()), bool(self.browser_var.get())
        s.sensor = {SENSORS[0]: "sim", SENSORS[1]: "webcam", SENSORS[2]: "phone"}.get(self.sensor_var.get(), "sim")
        s.camera = self._camera_value()
        save_settings(s)
        os.makedirs(s.shows_dir, exist_ok=True)
        cmd = master_command(s, show)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        self.remote_url = ""
        self.proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", env=env, creationflags=flags)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        self.btn.configure(text="Parar")
        self.edit_btn.configure(state="normal")
        self.status.set(f"Rodando o show “{show}”…")

    def _read(self, proc: subprocess.Popen) -> None:
        assert proc.stdout
        for line in proc.stdout:
            self.lines.put(line.rstrip())
        self.lines.put("\0fim")

    def _pump(self) -> None:
        try:
            while True:
                line = self.lines.get_nowait()
                if line == "\0fim":
                    code = self.proc.poll() if self.proc else 0
                    self.status.set("Parado." if code in (0, None, 1, -15, 15) else f"O mestre parou (código {code}). Veja o registro abaixo.")
                    self.btn.configure(text="Abrir")
                    self.edit_btn.configure(state="disabled")
                    self.phone_btn.configure(state="disabled")
                    continue
                url = remote_url_from_log(line)
                if url:
                    self.remote_url = url
                    self.phone_btn.configure(state="normal")
                    self.status.set(f"Rodando. Celular (mesma Wi-Fi): {url}")
                self._append(line)
        except queue.Empty:
            pass
        self.after(200, self._pump)

    def _append(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 400:
            self.log.delete("1.0", f"{lines - 400}.0")
        self.log.configure(state="disabled")

    def _stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _open_editor(self) -> None:
        webbrowser.open(f"http://localhost:{self.s.port}")

    def _copy_remote(self) -> None:
        if self.remote_url:
            self.clipboard_clear()
            self.clipboard_append(self.remote_url)
            self.status.set(f"Link copiado: {self.remote_url}  (ou use o QR no editor)")

    def _quit(self) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("ProjMap", "Fechar encerra o show em andamento. Fechar mesmo assim?"):
                return
            self._stop()
        self.destroy()


def _ask(parent: tk.Tk, title: str, prompt: str) -> str:
    from tkinter import simpledialog

    return simpledialog.askstring(title, prompt, parent=parent) or ""


def main() -> None:
    Launcher().mainloop()


if __name__ == "__main__":
    main()
