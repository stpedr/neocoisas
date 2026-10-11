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

export interface Output {
  width: number;
  height: number;
  intensity: number;
  blackout: boolean;
  pattern: Pattern;
  show_outlines: boolean;
  latency_ms: number;
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
}

export interface Look {
  id: string;
  name: string;
  surfaces: Record<string, { visible: boolean; opacity: number; source: SourceSpec }>;
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
}
