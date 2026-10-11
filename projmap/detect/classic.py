"""Detector clássico (só OpenCV): regiões de cor homogênea separadas por bordas.

Pipeline (foto reduzida para ~640 px no lado maior)::

    mean-shift (alisa textura, preserva bordas)
    → bordas Canny dilatadas = "muros" entre regiões
    → k-means de cor em Lab (K cresce com a sensibilidade)
    → componentes conexos por cor, sem atravessar as bordas
    → contorno → polígono simplificado → quadrilátero (o de maior IoU com a região)
    → nota = IoU(região, quad); NMS por IoU entre quads

Funciona bem com o que projeção mapeada costuma usar: paredes, portas, colunas,
caixas, painéis (regiões lisas de cor uniforme com arestas retas). Textura
forte, sombra dura e pouco contraste confundem; para isso entra o SAM 2.
"""

from __future__ import annotations

import cv2
import numpy as np

from .base import Candidate

WORK_SIZE = 640
LAB_WEIGHT = np.array([0.35, 1.0, 1.0], np.float32)  # claridade pesa menos que a cor
SAME_COLOR = 22.0  # distância Lab ponderada abaixo da qual duas regiões têm "a mesma cor"


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos como TL, TR, BR, BL (sentido horário na imagem)."""
    pts = np.asarray(pts, dtype=np.float64).reshape(4, 2)
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    pts = pts[np.argsort(ang)]  # horário (y para baixo), começando em algum canto
    start = int(np.argmin(pts.sum(axis=1)))  # TL = menor x+y
    return np.roll(pts, -start, axis=0)


def quad_candidates(contour: np.ndarray) -> list[np.ndarray]:
    """Quads possíveis para a região: casco convexo reduzido a 4 vértices em várias
    tolerâncias + o retângulo de área mínima (sempre válido)."""
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    out = []
    for k in np.linspace(0.005, 0.15, 30):
        approx = cv2.approxPolyDP(hull, k * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            out.append(order_quad(approx.reshape(4, 2)))
        if len(approx) < 4:
            break
    out.append(order_quad(cv2.boxPoints(cv2.minAreaRect(contour))))
    return out


def mask_iou(region: np.ndarray, quad: np.ndarray) -> float:
    qm = np.zeros_like(region)
    cv2.fillConvexPoly(qm, quad.round().astype(np.int32), 1)
    inter = np.count_nonzero(region & qm)
    union = np.count_nonzero(region | qm)
    return inter / union if union else 0.0


def fit_quad(contour: np.ndarray, region: np.ndarray) -> tuple[np.ndarray, float]:
    """Quad que melhor cobre a região, e a nota (1 = a região é um quadrilátero).

    O quad é ajustado ao **casco convexo** da região: algo na frente da
    superfície (um carrinho diante da porta, uma cadeira encostada na parede)
    "morde" a borda da região, e o casco ignora essas mordidas. A nota é a IoU
    com o casco, penalizada de leve pela solidez (região / casco), para que
    formas muito recortadas não pareçam quadriláteros perfeitos.
    """
    hull = cv2.convexHull(contour)
    hull_mask = np.zeros_like(region)
    cv2.fillConvexPoly(hull_mask, hull.reshape(-1, 2), 1)
    hull_area = np.count_nonzero(hull_mask)
    solidity = np.count_nonzero(region & hull_mask) / hull_area if hull_area else 0.0
    best, best_iou = None, -1.0
    for q in quad_candidates(contour):
        iou = mask_iou(hull_mask, q)
        if iou > best_iou:
            best, best_iou = q, iou
    return best, best_iou * float(np.sqrt(solidity))


def quad_iou(a: np.ndarray, b: np.ndarray, shape: tuple[int, int]) -> float:
    ma = np.zeros(shape, np.uint8)
    mb = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(ma, a.round().astype(np.int32), 1)
    cv2.fillConvexPoly(mb, b.round().astype(np.int32), 1)
    inter = np.logical_and(ma, mb).sum()
    union = np.logical_or(ma, mb).sum()
    return float(inter / union) if union else 0.0


class ClassicDetector:
    name = "classic"

    def detect(self, bgr: np.ndarray, sensitivity: float = 0.5, max_candidates: int = 12) -> list[Candidate]:
        s = float(np.clip(sensitivity, 0.0, 1.0))
        h0, w0 = bgr.shape[:2]
        k = WORK_SIZE / max(h0, w0)
        img = cv2.resize(bgr, (round(w0 * k), round(h0 * k)), interpolation=cv2.INTER_AREA) if k < 1 else bgr.copy()
        h, w = img.shape[:2]

        # 1) alisar textura mantendo bordas (madeira, reboco, ruído de celular)
        smooth = cv2.pyrMeanShiftFiltering(img, sp=12, sr=int(28 - 12 * s))

        # 2) bordas = barreiras entre regiões vizinhas de cor parecida (ex.: as duas paredes de uma quina)
        gray = cv2.cvtColor(smooth, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, int(60 - 35 * s), int(140 - 70 * s))
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

        # 3) k-means de cor em Lab
        lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
        # Menos peso para a claridade: a luz varia ao longo de uma mesma parede ou
        # porta (gradiente) e não deve partir a superfície em faixas.
        lab *= LAB_WEIGHT
        n_clusters = int(round(5 + 7 * s))
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        cv2.setRNGSeed(7)  # resultado reprodutível
        _, labels, centers = cv2.kmeans(lab, n_clusters, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
        labels = merge_close_clusters(labels.ravel(), centers, 10.0 - 4.0 * s).reshape(h, w)

        # 4) componentes conexos por cor, cortados pelas bordas
        min_area = (0.025 - 0.02 * s) * h * w
        kernel = np.ones((5, 5), np.uint8)
        min_score = 0.62 - 0.12 * s
        raw: list[tuple[float, np.ndarray, np.ndarray, np.ndarray]] = []
        for c in range(n_clusters):
            mask = ((labels == c) & (edges == 0)).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            n, comp, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
            pieces = [
                fill_holes(cv2.morphologyEx((comp == i).astype(np.uint8), cv2.MORPH_CLOSE, kernel, iterations=2))
                for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area / 4
            ]
            for region in merge_occluded(pieces):
                if np.count_nonzero(region) < min_area:
                    continue
                fitted = self._fit(region)
                if fitted:
                    raw.append(fitted)

        # 5) melhores primeiro (retangular e grande), sem duplicatas nem contidos
        raw.sort(key=lambda r: r[0] * np.sqrt(cv2.contourArea(r[2])), reverse=True)
        out: list[Candidate] = []
        kept: list[np.ndarray] = []
        kept_masks: list[tuple[np.ndarray, np.ndarray]] = []  # (máscara do quad, cor Lab ponderada)
        for score, quad, cnt, region in raw:
            if score < min_score:
                continue
            if any(quad_iou(quad, q, (h, w)) > 0.5 for q in kept):
                continue
            qm = np.zeros((h, w), np.uint8)
            cv2.fillConvexPoly(qm, quad.round().astype(np.int32), 1)
            mean_bgr = cv2.mean(img, mask=region)[:3]
            lab = _lab((int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0]))) * LAB_WEIGHT
            similar = np.zeros((h, w), np.uint8)
            for m, other in kept_masks:
                if np.linalg.norm(lab - other) < SAME_COLOR:
                    similar |= m
            if np.count_nonzero(qm & similar) > 0.6 * np.count_nonzero(qm):
                continue  # faixa de uma superfície da mesma cor já aceita (ex.: teto em degradê)
            kept.append(quad)
            kept_masks.append((qm, lab))
            peri = cv2.arcLength(cnt, True)
            poly = cv2.approxPolyDP(cnt, 0.008 * peri, True).reshape(-1, 2)
            mean_bgr = cv2.mean(img, mask=region)[:3]
            out.append(Candidate(
                quad=[(float(x / w), float(y / h)) for x, y in quad],
                polygon=[(float(x / w), float(y / h)) for x, y in poly],
                area=float(cv2.contourArea(cnt) / (h * w)),
                score=round(float(score), 3),
                label=f"Região {len(out) + 1}",
                color=(int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])),
            ))
            if len(out) >= max_candidates:
                break
        return drop_nested(out, (h, w))

    @staticmethod
    def _fit(region: np.ndarray):
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        cnt = max(contours, key=cv2.contourArea)
        quad, score = fit_quad(cnt, region)
        return (score, quad, cnt, region) if quad is not None else None


def merge_close_clusters(labels: np.ndarray, centers: np.ndarray, max_dist: float) -> np.ndarray:
    """Une grupos de cor cujos centros distam menos que ``max_dist`` (Lab ponderado).

    O k-means sempre devolve K grupos. Numa cena de poucas cores, ele parte
    cada cor pelo ruído do sensor, e a superfície se fragmenta. Unir centros
    próximos deixa o número efetivo de cores se adaptar à foto.
    """
    k = len(centers)
    parent = list(range(k))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(k):
        for j in range(i + 1, k):
            if np.linalg.norm(centers[i] - centers[j]) < max_dist:
                parent[find(i)] = find(j)
    roots = np.array([find(i) for i in range(k)])
    return roots[labels]


def _lab(rgb: tuple[int, int, int]) -> np.ndarray:
    px = np.uint8([[[rgb[2], rgb[1], rgb[0]]]])
    return cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)


def drop_nested(cands: list[Candidate], shape: tuple[int, int], frac: float = 0.8,
                same_color: float = SAME_COLOR) -> list[Candidate]:
    """Remove o candidato quase todo (``frac``) dentro de um MAIOR **de cor parecida**.

    - Mancha de luz no meio da porta (mesma cor, mais clara): é a mesma
      superfície, sai.
    - Porta numa parede, quadro numa parede (outra cor): são superfícies
      distintas, ficam as duas.
    A cor compara-se em Lab, com a claridade pesando menos (ver o k-means).
    """
    h, w = shape
    masks = []
    for c in cands:
        m = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(m, (np.array(c.quad) * [w, h]).round().astype(np.int32), 1)
        masks.append(m)
    areas = [np.count_nonzero(m) for m in masks]
    labs = [_lab(c.color) * LAB_WEIGHT for c in cands]
    keep = []
    for i, c in enumerate(cands):
        nested = any(
            j != i and areas[j] > areas[i]
            and np.count_nonzero(masks[i] & masks[j]) > frac * areas[i]
            and np.linalg.norm(labs[i] - labs[j]) < same_color
            for j in range(len(cands))
        )
        if not nested:
            keep.append(c)
    for n, c in enumerate(keep, 1):
        c.label = f"Região {n}"
    return keep


def fill_holes(region: np.ndarray) -> np.ndarray:
    """Preenche buracos da região: uma mancha de luz, um quadro na parede ou um
    reflexo viram outra cor no meio da superfície, mas não a interrompem."""
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(region)
    cv2.drawContours(out, contours, -1, 1, thickness=cv2.FILLED)
    return out


def _quad_score(region: np.ndarray) -> float:
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    cnt = np.vstack(contours)  # pedaços separados entram juntos no casco
    best = 0.0
    for q in quad_candidates(cnt):
        best = max(best, mask_iou(region, q))
    return best


def merge_occluded(pieces: list[np.ndarray], gap: int = 15) -> list[np.ndarray]:
    """Junta pedaços da MESMA cor que são uma superfície cortada por algo na frente.

    Uma porta com uma fita pendurada, ou atrás de um carrinho, vira vários
    pedaços. Dois pedaços próximos (até ``gap`` px) se juntam quando o
    quadrilátero da união cobre a região tão bem quanto o maior pedaço sozinho,
    descontando o vão do objeto (conta-se a área do quad, não só os pixels).
    """
    pieces = [p for p in pieces if np.count_nonzero(p)]
    if len(pieces) < 2:
        return pieces
    k = np.ones((2 * gap + 1, 2 * gap + 1), np.uint8)  # alcança pedaços a até `gap` px
    changed = True
    while changed and len(pieces) > 1:
        changed = False
        pieces.sort(key=np.count_nonzero, reverse=True)
        grown = [cv2.dilate(p, k) for p in pieces]
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                if not np.any(grown[i] & pieces[j]):
                    continue
                union = pieces[i] | pieces[j]
                # Preenche o vão entre os pedaços (o objeto na frente) antes de avaliar.
                closed = cv2.morphologyEx(union, cv2.MORPH_CLOSE, np.ones((gap * 2 + 1, gap * 2 + 1), np.uint8))
                s_union = _quad_score(closed)
                if s_union >= min(max(_quad_score(pieces[i]), _quad_score(pieces[j])), 0.95) - 0.05:
                    pieces[i] = closed
                    del pieces[j]
                    changed = True
                    break
            if changed:
                break
    return pieces
