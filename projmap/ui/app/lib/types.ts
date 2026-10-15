// Espelho dos modelos pydantic de projmap/core/project.py (fonte de verdade).

export type Point = [number, number];
export type Quad = [Point, Point, Point, Point];

export type MediaKind = "video" | "image" | "gif";
export type SourceKind = "none" | "video" | "image" | "gif" | "color" | "test" | "interactive";
export type Pattern = "none" | "white" | "grid" | "edges" | "black";
export type Fit = "stretch" | "cover" | "contain";
export type BlendMode = "normal" | "add" | "multiply";

export interface MediaItem {
  sha256: string;
  filename: string;
  ext: string;
  kind: MediaKind;
  size_bytes: number;
}

// Ajuste de imagem (espelho de projmap/core/project.py::ColorAdjust). Neutro = DEFAULT_COLOR.
export interface ColorAdjust {
  brightness: number;
  contrast: number;
  saturation: number;
  gamma: number;
  temperature: number;
}

export const DEFAULT_COLOR: ColorAdjust = { brightness: 1, contrast: 1, saturation: 1, gamma: 1, temperature: 0 };

export interface Output {
  width: number;
  height: number;
  intensity: number;
  blackout: boolean;
  pattern: Pattern;
  show_outlines: boolean;
  latency_ms: number;
  color: ColorAdjust;
  flip_h: boolean;
  flip_v: boolean;
}

export interface Node {
  id: string;
  name: string;
  output: Output;
  photo: string | null;
  photo_boundary: Point[];
}

export interface SourceSpec {
  kind: SourceKind;
  media: string | null;
  color: [number, number, number];
  fit: Fit;
  loop: boolean;
  speed: number;
  offset_s: number;
}

// Mídia extra por cima do fundo da superfície (F9). rect = [x, y, w, h] em uv da superfície.
export interface Layer {
  id: string;
  label: string;
  visible: boolean;
  source: SourceSpec;
  rect: [number, number, number, number];
  opacity: number;
}

export interface Surface {
  id: string;
  label: string;
  node_id: string;
  z: number;
  visible: boolean;
  polygon_src: Point[] | null;
  warp: { type: "homography"; base: Point[] };
  source: SourceSpec;
  opacity: number;
  feather: number;
  blend_mode: BlendMode;
  layers: Layer[];
  color: ColorAdjust;
}

export interface Look {
  id: string;
  name: string;
  surfaces: Record<string, { visible: boolean; opacity: number; source: SourceSpec; layers?: Layer[] | null }>;
}

export interface Project {
  version: number;
  name: string;
  fps: number;
  nodes: Node[];
  surfaces: Surface[];
  media: Record<string, MediaItem>;
  looks: Look[];
}

export const DEFAULT_SOURCE: SourceSpec = {
  kind: "test",
  media: null,
  color: [255, 255, 255],
  fit: "stretch",
  loop: true,
  speed: 1,
  offset_s: 0,
};

// ---- detecção de superfícies (F3): coordenadas normalizadas da foto [0,1]
export interface DetectCandidate {
  quad: Point[]; // TL, TR, BR, BL
  polygon: Point[];
  area: number;
  score: number;
  label: string;
  color: [number, number, number];
}

// ---- galeria: biblioteca de pastas (ex.: Google Drive sincronizado) e mídias do projeto
export interface LibraryItem {
  id: string;
  name: string;
  folder: string;
  kind: MediaKind;
  size_bytes: number;
  width: number;
  height: number;
  duration: number;
  aspect: number;
}

export interface MediaInfo extends MediaItem {
  width: number;
  height: number;
  duration: number;
  aspect: number;
}

export interface Suggestion {
  ref: string; // "lib:<id>" ou "sha:<sha256>"
  name: string;
  kind: MediaKind;
  score: number;
  reasons: string[];
}

// ---- camada interativa (projmap/interact)
export interface InteractEntity {
  id: number;
  group: string;
  x: number;
  y: number;
  state: "idle" | "move" | "frozen" | "shy";
}

export interface InteractPlayer {
  id: number;
  x: number;
  distance: number;
  yaw_deg: number;
  tracked: boolean;
  watching: boolean;
  gaze: [number, number, number];
}

export interface InteractState {
  spec: { title: string; description: string; groups: { name: string; sprite: string; count: number }[] } & Record<string, unknown>;
  sensor: "sim" | "osc" | "webcam" | "phone";
  phone?: { connected: number; fps: number } | null;
  scripted: boolean;
  paused: boolean;
  debug: boolean;
  tick: number;
  entities: InteractEntity[];
  players: InteractPlayer[];
  events: { name: string; entity_id: number; t: number }[];
  source?: "llm" | "fallback";
  notes?: string[];
  effect?: string | null;
  effect_status?: string;
  effect_params?: EffectParams | null;
}

// Efeitos importados do visual_frames (projmap/effects)
export interface EffectParams {
  orbes_maos: boolean;
  cor_segue_musica: boolean;
  matiz_fixo: number;
  sensibilidade_som: number;
  quantidade_ecos: number;
  distancia_ecos: number;
  tamanho_peca: number;
  lego_cair: boolean;
  animal: number;          // 0 gato, 1 dinossauro, 2 coelho
  fundo_colorido: boolean;
  intervalo_aviao: number;
  brilho: number;
}

export interface EffectsCatalog {
  imported: boolean;
  hint: string;
  effects: Record<string, { title: string; description: string; available: boolean }>;
}

// ---- presets de imagem do operador (projmap/color_presets.py)
export interface ColorPreset {
  id: string;
  name: string;
  color: ColorAdjust;
}

// ---- Google Drive na galeria (projmap/gdrive.py)
export interface DriveStatus {
  mode: "off" | "oauth" | "apikey";
  configured: boolean;
  connected: boolean;
  root: string;
  folder_set: boolean;
  can_configure: boolean;
}

export interface DriveEntry {
  id: string;
  name: string;
  kind: "folder" | MediaKind;
  size_bytes: number;
  modified: string;
  width: number;
  height: number;
  duration: number;
  aspect: number;
  has_thumb: boolean;
}

export interface DriveListing {
  folder: { id: string; name: string };
  folders: DriveEntry[];
  items: DriveEntry[];
}
