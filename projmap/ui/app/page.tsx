"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor, { type Mode, type View } from "./components/Editor";
import InteractPanel from "./components/InteractPanel";
import RemoteCard from "./components/RemoteCard";
import SurfacePanel from "./components/SurfacePanel";
import LayersPanel from "./components/LayersPanel";
import DetectPanel from "./components/DetectPanel";
import LibraryCard from "./components/LibraryCard";
import MediaGallery from "./components/MediaGallery";
import SuggestAll from "./components/SuggestAll";
import { api, ApiError } from "./lib/api";
import { applyH, invert3, mul3, photoToProjector, rectQuad, validateQuad } from "./lib/geometry";
import type { DetectCandidate, MediaItem, Output, Pattern, Point, Project, Surface } from "./lib/types";
import { DEFAULT_SOURCE } from "./lib/types";

type SaveState = "idle" | "saving" | "saved" | "error";

const PATTERNS: { id: Pattern; label: string }[] = [
  { id: "none", label: "Conteúdo" },
  { id: "grid", label: "Grade" },
  { id: "edges", label: "Bordas da foto" },
  { id: "white", label: "Branco" },
  { id: "black", label: "Preto" },
];

export default function Page() {
  const [project, setProject] = useState<Project | null>(null);
  const [nodeId, setNodeId] = useState<string>("");
  const [view, setView] = useState<View>("photo");
  const [mode, setMode] = useState<Mode>("surfaces");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedCorner, setSelectedCorner] = useState<number | null>(null);
  const [photo, setPhoto] = useState<HTMLImageElement | null>(null);
  const [save, setSave] = useState<SaveState>("idle");
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "err" } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);
  const [showMedia, setShowMedia] = useState(true);
  const [gallery, setGallery] = useState<{ surfaceId: string | null; title: string; onPick: (m: MediaItem) => void } | null>(null);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [cands, setCands] = useState<DetectCandidate[]>([]);
  const [candOn, setCandOn] = useState<Set<number>>(new Set());
  const toggleCand = (i: number) =>
    setCandOn((cur) => {
      const next = new Set(cur);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  // ---- salvamento: um PUT por vez, sempre com o estado mais recente.
  // Enquanto o usuário arrasta, os PUTs se encadeiam (~20/s) e a parede acompanha.
  const pending = useRef<Project | null>(null);
  const inflight = useRef(false);
  // Revisão que este editor conhece. Se o mestre avançar sem ele (remote no
  // celular, looks), recarrega antes que o próximo PUT apague a mudança alheia.
  const knownRev = useRef(-1);
  const flush = useCallback(async () => {
    if (inflight.current || !pending.current) return;
    const next = pending.current;
    pending.current = null;
    inflight.current = true;
    setSave("saving");
    try {
      const { revision } = await api.putProject(next);
      knownRev.current = revision;
      setSave(pending.current ? "saving" : "saved");
    } catch (e) {
      setSave("error");
      notify(e instanceof ApiError ? e.message : "Falha ao salvar (mestre offline?)", "err");
    } finally {
      inflight.current = false;
      if (pending.current) void flush();
    }
  }, []);

  const commit = useCallback(
    (next: Project) => {
      setProject(next);
      pending.current = next;
      void flush();
    },
    [flush],
  );

  const toastTimer = useRef<number | undefined>(undefined);
  function notify(msg: string, kind: "ok" | "err" = "ok") {
    setToast({ msg, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }

  // ---- carga inicial
  useEffect(() => {
    api
      .getProject()
      .then(({ revision, project }) => {
        knownRev.current = revision;
        setProject(project);
        setNodeId(project.nodes[0]?.id ?? "");
      })
      .catch(() => setLoadError("Não foi possível falar com o mestre. Ele está rodando? (python -m projmap.master)"));
  }, []);

  // ---- sincronia com outros clientes (remote no celular)
  useEffect(() => {
    const id = window.setInterval(async () => {
      if (inflight.current || pending.current) return;
      try {
        const { revision } = await api.health();
        if (revision === knownRev.current || inflight.current || pending.current) return;
        const fresh = await api.getProject();
        if (inflight.current || pending.current) return;
        knownRev.current = fresh.revision;
        setProject(fresh.project);
      } catch {
        /* mestre reiniciando: tenta de novo no próximo ciclo */
      }
    }, 1500);
    return () => window.clearInterval(id);
  }, []);

  const node = project?.nodes.find((n) => n.id === nodeId) ?? null;
  const surfaces = useMemo(() => (project ? project.surfaces.filter((s) => s.node_id === nodeId) : []), [project, nodeId]);
  const selected = surfaces.find((s) => s.id === selectedId) ?? null;

  // ---- foto do nó
  useEffect(() => {
    if (!node?.photo) {
      setPhoto(null);
      return;
    }
    const img = new Image();
    img.onload = () => setPhoto(img);
    img.onerror = () => setPhoto(null);
    img.src = api.photoUrl(node.id, String(photoVersion));
  }, [node?.id, node?.photo, photoVersion]);

  const photoToProj = useMemo(() => {
    if (!node || !photo) return null;
    return photoToProjector(node.photo_boundary, photo.naturalWidth, photo.naturalHeight, node.output.width, node.output.height);
  }, [node, photo]);

  // ---- edição
  // Sempre o projeto mais recente: depois de um upload (await), o `project`
  // do fechamento ainda não tem a mídia nova e o PUT seria recusado.
  const latest = useRef<Project | null>(null);
  latest.current = project;
  const updateSurface = useCallback(
    (id: string, fn: (s: Surface) => Surface) => {
      const cur = latest.current;
      if (!cur) return;
      const next = { ...cur, surfaces: cur.surfaces.map((s) => (s.id === id ? fn(s) : s)) };
      latest.current = next;
      commit(next);
    },
    [commit],
  );

  const onQuad = useCallback(
    (id: string, quad: Point[]) => updateSurface(id, (s) => ({ ...s, warp: { ...s.warp, base: quad } })),
    [updateSurface],
  );

  // Mover a área projetada mantém as superfícies "presas" à foto: elas marcam
  // coisas físicas da parede, então o que muda é onde caem no projetor.
  const onBoundary = useCallback(
    (boundary: Point[]) => {
      if (!project || !node || !photo) return;
      const oldH = photoToProj;
      const newH = photoToProjector(boundary, photo.naturalWidth, photo.naturalHeight, node.output.width, node.output.height);
      const oldInv = oldH ? invert3(oldH) : null;
      if (!newH || !oldInv) return;
      const t = mul3(newH, oldInv);
      const moved = project.surfaces.map((s) =>
        s.node_id !== node.id ? s : { ...s, warp: { ...s.warp, base: s.warp.base.map((p) => applyH(t, p as Point)) } },
      );
      if (moved.some((s) => s.node_id === node.id && validateQuad(s.warp.base as Point[]))) return;
      commit({
        ...project,
        surfaces: moved,
        nodes: project.nodes.map((n) => (n.id === node.id ? { ...n, photo_boundary: boundary } : n)),
      });
    },
    [project, node, photo, photoToProj, commit],
  );

  const patchOutput = async (changes: Partial<Output>) => {
    if (!node || !project) return;
    // Otimista: a UI responde já; o PATCH é a fonte de verdade.
    setProject({ ...project, nodes: project.nodes.map((n) => (n.id === node.id ? { ...n, output: { ...n.output, ...changes } } : n)) });
    try {
      const { project: fresh } = await api.patchOutput(node.id, changes);
      setProject((cur) => (cur ? { ...cur, nodes: fresh.nodes } : fresh));
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Falha ao enviar comando", "err");
    }
  };

  const addSurface = () => {
    if (!project || !node) return;
    const n = surfaces.length + 1;
    let quad: Point[];
    if (view === "photo" && photo && photoToProj) {
      // Nasce no centro da FOTO (onde o usuário está olhando) e vai para o projetor.
      const w = photo.naturalWidth;
      const h = photo.naturalHeight;
      const s = Math.min(w, h) * 0.25;
      quad = rectQuad(w / 2 - s / 2 + n * 12, h / 2 - s / 2 + n * 12, s, s).map((p) => applyH(photoToProj, p));
    } else {
      const { width: w, height: h } = node.output;
      quad = rectQuad(w * 0.35 + n * 16, h * 0.3 + n * 16, w * 0.3, h * 0.4);
    }
    quad = quad.map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100]);
    const id = uniqueId(project, "superficie");
    const surface: Surface = {
      id,
      label: `Superfície ${n}`,
      node_id: node.id,
      z: Math.max(0, ...surfaces.map((s) => s.z + 1)),
      visible: true,
      polygon_src: null,
      warp: { type: "homography", base: quad },
      source: { ...DEFAULT_SOURCE },
      opacity: 1,
      feather: 0,
      blend_mode: "normal",
      layers: [],
    };
    commit({ ...project, surfaces: [...project.surfaces, surface] });
    setSelectedId(id);
    setSelectedCorner(null);
    setMode("surfaces");
  };

  // ---- detecção (F3): candidatos em coordenadas normalizadas da foto
  const createFromCandidates = () => {
    const cur = latest.current;
    if (!cur || !node || !photo || !photoToProj) return;
    const added: Surface[] = [];
    const skipped: string[] = [];
    let z = Math.max(0, ...surfaces.map((s) => s.z + 1));
    const ids = { surfaces: [...cur.surfaces] } as Project;
    [...candOn].sort((a, b) => a - b).forEach((i) => {
      const c = cands[i];
      const quad = c.quad
        .map(([x, y]) => applyH(photoToProj, [x * photo.naturalWidth, y * photo.naturalHeight]))
        .map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100] as Point);
      if (validateQuad(quad)) {
        skipped.push(c.label);
        return;
      }
      const id = uniqueId({ ...ids, surfaces: [...ids.surfaces, ...added] } as Project, "superficie");
      added.push({
        id,
        label: c.label,
        node_id: node.id,
        z: z++,
        visible: true,
        polygon_src: c.polygon,
        warp: { type: "homography", base: quad },
        source: { ...DEFAULT_SOURCE },
        opacity: 1,
        feather: 0,
        blend_mode: "normal",
        layers: [],
      });
    });
    if (added.length) {
      const next = { ...cur, surfaces: [...cur.surfaces, ...added] };
      latest.current = next;
      commit(next);
      setSelectedId(added[0].id);
      setSelectedLayerId(null);
    }
    setCands([]);
    setCandOn(new Set());
    notify(
      `${added.length} superfície(s) criada(s).` +
        (skipped.length ? ` Ignoradas (fora da área projetada): ${skipped.join(", ")}.` : " Ajuste os cantos se precisar."),
      skipped.length ? "err" : "ok",
    );
  };

  // Mídia importada da galeria entra no estado sem recarregar o projeto inteiro.
  const rememberMedia = (item: MediaItem) => {
    const cur = latest.current;
    if (cur && !cur.media[item.sha256]) {
      const next = { ...cur, media: { ...cur.media, [item.sha256]: item } };
      latest.current = next;
      setProject(next);
    }
  };

  const openGallery = (surfaceId: string | null, title: string) => (onPick: (m: MediaItem) => void) =>
    setGallery({ surfaceId, title, onPick: (m) => { rememberMedia(m); onPick(m); } });

  const applySuggestions = (picks: { surfaceId: string; item: MediaItem }[]) => {
    picks.forEach((p) => rememberMedia(p.item));
    const cur = latest.current;
    if (!cur) return;
    const bySurface = new Map(picks.map((p) => [p.surfaceId, p.item]));
    const next = {
      ...cur,
      surfaces: cur.surfaces.map((s) => {
        const m = bySurface.get(s.id);
        return m ? { ...s, source: { ...s.source, kind: m.kind, media: m.sha256 } } : s;
      }),
    };
    latest.current = next;
    commit(next);
    notify(`Mídia aplicada em ${picks.length} superfície(s).`);
  };

  const uploadMedia = async (file: File) => {
    const { item } = await api.uploadMedia(file);
    // Junta só a mídia nova ao estado atual: um getProject() inteiro poderia
    // atropelar edições ainda não salvas.
    const cur = latest.current;
    if (cur) {
      const next = { ...cur, media: { ...cur.media, [item.sha256]: item } };
      latest.current = next;
      setProject(next);
    }
    return item;
  };

  const deleteSurface = (id: string) => {
    if (!project) return;
    commit({ ...project, surfaces: project.surfaces.filter((s) => s.id !== id) });
    setSelectedId(null);
  };

  // ---- teclado: ajuste fino de 1 px do projetor (Shift = 10 px)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (!selected) return;
      if (e.key === "Tab") {
        e.preventDefault();
        setSelectedCorner((c) => (c === null ? 0 : (c + (e.shiftKey ? 3 : 1)) % 4));
        return;
      }
      if (e.key === "Escape") return setSelectedCorner(null);
      const step = e.shiftKey ? 10 : 1;
      const d: Record<string, Point> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
      const delta = d[e.key];
      if (!delta) return;
      e.preventDefault();
      const quad = selected.warp.base.map((p, i) =>
        selectedCorner === null || i === selectedCorner ? ([p[0] + delta[0], p[1] + delta[1]] as Point) : (p as Point),
      );
      if (!validateQuad(quad)) onQuad(selected.id, quad);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, selectedCorner, onQuad]);

  const uploadPhoto = async (file: File) => {
    if (!node) return;
    try {
      const { project: fresh } = await api.uploadPhoto(node.id, file);
      setProject(fresh);
      setPhotoVersion((v) => v + 1);
      setView("photo");
      setMode("boundary");
      notify("Foto carregada. Agora marque os 4 cantos da área projetada.");
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Falha no upload", "err");
    }
  };

  if (loadError) return <main className="center-msg">{loadError}</main>;
  if (!project || !node) return <main className="center-msg">Carregando projeto…</main>;
  const out = node.output;

  return (
    <main className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>◆</span>
          <input
            className="project-name"
            value={project.name}
            aria-label="Nome do projeto"
            onChange={(e) => commit({ ...project, name: e.target.value })}
          />
          <span className={`save save-${save}`}>{{ idle: "", saving: "Salvando…", saved: "Salvo", error: "Erro ao salvar" }[save]}</span>
        </div>
        <div className="output-controls" role="group" aria-label="Saída do projetor">
          <div className="segmented">
            {PATTERNS.map((p) => (
              <button key={p.id} className={out.pattern === p.id ? "on" : ""} onClick={() => patchOutput({ pattern: p.id })}>
                {p.label}
              </button>
            ))}
          </div>
          <label className="toggle">
            <input type="checkbox" checked={out.show_outlines} onChange={(e) => patchOutput({ show_outlines: e.target.checked })} />
            Contornos
          </label>
          <label className="slider" title="Dimmer master do projetor">
            Intensidade
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={out.intensity}
              onChange={(e) => patchOutput({ intensity: Number(e.target.value) })}
            />
          </label>
          <button
            className={`btn ${out.blackout ? "btn-danger" : ""}`}
            title="Apaga o projetor na hora (tela preta) sem perder nada do mapeamento. Use entre cenas, para ajustar algo na parede ou numa emergência. Clique de novo para voltar."
            onClick={() => patchOutput({ blackout: !out.blackout })}
          >
            {out.blackout ? "Blackout ATIVO" : "Blackout"}
          </button>
          <a
            className="btn"
            href={api.exportUrl()}
            title="Baixa o projeto inteiro (mapeamento, mídias e foto) num único arquivo .pmz: serve de backup ou para abrir o show em outro computador."
          >
            Exportar .pmz
          </a>
        </div>
      </header>

      <section className="workspace">
        <div className="stage">
          <div className="stage-bar">
            <div className="segmented">
              <button className={view === "photo" ? "on" : ""} onClick={() => setView("photo")} disabled={!photo}>
                Foto
              </button>
              <button className={view === "projector" ? "on" : ""} onClick={() => { setView("projector"); setMode("surfaces"); }}>
                Projetor
              </button>
            </div>
            <label className="toggle" title="Mostra vídeo, GIF e imagem dentro das superfícies">
              <input type="checkbox" checked={showMedia} onChange={(e) => setShowMedia(e.target.checked)} />
              Prévia da mídia
            </label>
            <span className="hint">
              {mode === "boundary"
                ? "Arraste os 4 cantos amarelos até onde o quadro BRANCO do projetor aparece na foto."
                : "Arraste cantos ou a superfície inteira. Setas = 1 px (Shift = 10), Tab troca o canto."}
            </span>
          </div>
          <Editor
            node={node}
            surfaces={surfaces}
            view={photo ? view : "projector"}
            mode={mode}
            photo={photo}
            photoToProj={photoToProj}
            selectedId={selectedId}
            selectedCorner={selectedCorner}
            onSelect={(id, c) => {
              if (id !== selectedId) setSelectedLayerId(null);
              setSelectedId(id);
              setSelectedCorner(c);
            }}
            onQuad={onQuad}
            onBoundary={onBoundary}
            onReject={(m) => notify(m, "err")}
            media={project.media}
            showMedia={showMedia}
            selectedLayerId={selectedLayerId}
            candidates={cands}
            candidateOn={candOn}
            onToggleCandidate={toggleCand}
            onLayerRect={(sid, lid, rect) =>
              updateSurface(sid, (s) => ({ ...s, layers: s.layers.map((l) => (l.id === lid ? { ...l, rect } : l)) }))
            }
          />
        </div>

        <aside className="panel">
          <section className="card">
            <h2>1 · Foto da posição do projetor</h2>
            <p className="dim">Tire a foto com a câmera no lugar do projetor. No celular, o botão abre a câmera.</p>
            <label className="btn btn-block">
              {node.photo ? "Trocar foto" : "Enviar / tirar foto"}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])}
              />
            </label>
          </section>

          <DetectPanel
            nodeId={node.id}
            hasPhoto={!!photo}
            candidates={cands}
            selected={candOn}
            onResult={(c) => {
              setCands(c);
              // Pré-marca as regiões grandes e razoavelmente retangulares (paredes, portas,
              // teto); objetos soltos costumam ser pequenos. O operador ajusta a seleção.
              setCandOn(new Set(c.map((x, i) => (x.area >= 0.04 && x.score >= 0.55 ? i : -1)).filter((i) => i >= 0)));
              setView("photo");
              setMode("surfaces");
            }}
            onToggle={toggleCand}
            onCreate={createFromCandidates}
            onClear={() => {
              setCands([]);
              setCandOn(new Set());
            }}
            onError={(m) => notify(m, "err")}
          />

          <section className="card">
            <h2>2 · Área projetada</h2>
            <p className="dim">
              Projete <b>Branco</b>, veja onde a luz cai na foto e marque os 4 cantos. Depois use <b>Bordas da foto</b> para conferir na parede.
            </p>
            <button
              className={`btn btn-block ${mode === "boundary" ? "btn-accent" : ""}`}
              disabled={!photo}
              onClick={() => {
                setView("photo");
                setMode(mode === "boundary" ? "surfaces" : "boundary");
              }}
            >
              {mode === "boundary" ? "Concluir marcação" : "Marcar área projetada"}
            </button>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>3 · Superfícies</h2>
              <div className="row">
                {surfaces.length > 0 && (
                  <button className="btn btn-small" title="Sugere uma mídia para cada superfície (formato e resolução)" onClick={() => setSuggestOpen(true)}>
                    ⭐ Sugerir mídias
                  </button>
                )}
                <button className="btn btn-accent btn-small" onClick={addSurface}>
                  + Nova
                </button>
              </div>
            </div>
            {surfaces.length === 0 ? (
              <p className="dim">Nenhuma superfície. Crie uma e arraste os cantos sobre a parede/coluna/caixa.</p>
            ) : (
              <ul className="surface-list">
                {[...surfaces]
                  .sort((a, b) => b.z - a.z)
                  .map((s) => (
                    <li key={s.id}>
                      <button
                        className={s.id === selectedId ? "on" : ""}
                        onClick={() => {
                          setSelectedId(s.id);
                          setSelectedCorner(null);
                          setMode("surfaces");
                        }}
                      >
                        <span className="dot" data-visible={s.visible} />
                        {s.label || s.id}
                        <span className="dim small">{sourceLabel(s)}</span>
                      </button>
                    </li>
                  ))}
              </ul>
            )}
          </section>

          {selected && (
            <SurfacePanel
              key={selected.id}
              surface={selected}
              project={project}
              onChange={(fn) => updateSurface(selected.id, fn)}
              onDelete={() => deleteSurface(selected.id)}
              onUpload={uploadMedia}
              onError={(m) => notify(m, "err")}
              onOpenGallery={openGallery(selected.id, `Mídia de "${selected.label || selected.id}"`)}
            />
          )}

          {selected && (
            <LayersPanel
              key={`layers-${selected.id}`}
              surface={selected}
              project={project}
              selectedLayerId={selectedLayerId}
              onSelectLayer={setSelectedLayerId}
              onChange={(fn) => updateSurface(selected.id, fn)}
              onUpload={uploadMedia}
              onError={(m) => notify(m, "err")}
              onOpenGallery={openGallery(selected.id, `Camada em "${selected.label || selected.id}"`)}
            />
          )}

          <LibraryCard onError={(m) => notify(m, "err")} onOk={(m) => notify(m)} />

          <RemoteCard />

          <InteractPanel onError={(m) => notify(m, "err")} />

          <section className="card">
            <h2>Projetor</h2>
            <div className="row">
              <label>
                Largura
                <input
                  type="number"
                  min={16}
                  value={out.width}
                  onChange={(e) => commitOutputSize(Number(e.target.value), out.height)}
                />
              </label>
              <label>
                Altura
                <input
                  type="number"
                  min={16}
                  value={out.height}
                  onChange={(e) => commitOutputSize(out.width, Number(e.target.value))}
                />
              </label>
            </div>
            <p className="dim small">Use a resolução nativa do projetor (ex.: 1920×1080).</p>
          </section>
        </aside>
      </section>

      <MediaGallery
        open={!!gallery}
        title={gallery?.title}
        surfaceId={gallery?.surfaceId}
        onPick={(m) => gallery?.onPick(m)}
        onClose={() => setGallery(null)}
        onError={(m) => notify(m, "err")}
      />
      <SuggestAll
        open={suggestOpen}
        surfaces={surfaces}
        onApply={applySuggestions}
        onClose={() => setSuggestOpen(false)}
        onError={(m) => notify(m, "err")}
      />

      {toast && (
        <div className={`toast toast-${toast.kind}`} role="status">
          {toast.msg}
        </div>
      )}
    </main>
  );

  function commitOutputSize(w: number, h: number) {
    if (!project || !node || !(w >= 16 && h >= 16)) return;
    // Mudar a resolução escala as superfícies junto (continuam no mesmo lugar da parede).
    const sx = w / node.output.width;
    const sy = h / node.output.height;
    commit({
      ...project,
      nodes: project.nodes.map((n) => (n.id === node.id ? { ...n, output: { ...n.output, width: w, height: h } } : n)),
      surfaces: project.surfaces.map((s) =>
        s.node_id !== node.id ? s : { ...s, warp: { ...s.warp, base: s.warp.base.map(([x, y]) => [x * sx, y * sy] as Point) } },
      ),
    });
  }
}

function uniqueId(project: Project, prefix: string) {
  const used = new Set(project.surfaces.map((s) => s.id));
  for (let i = 1; ; i++) if (!used.has(`${prefix}-${i}`)) return `${prefix}-${i}`;
}

function sourceLabel(s: Surface) {
  return { none: "vazia", video: "vídeo", image: "imagem", gif: "GIF", color: "cor", test: "cartela", interactive: "interativa" }[s.source.kind];
}
