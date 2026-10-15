import { describe, expect, it } from "vitest";
import {
  applyH,
  homography4,
  invert3,
  mul3,
  pointInQuad,
  rectQuad,
  validateQuad,
  type Mat3,
} from "./geometry";
import type { Point } from "./types";

const IDENTITY: Mat3 = [1, 0, 0, 0, 1, 0, 0, 0, 1];

describe("applyH", () => {
  it("a matriz identidade não move o ponto", () => {
    expect(applyH(IDENTITY, [10, 20])).toEqual([10, 20]);
  });

  it("divide por w (projeção homogênea)", () => {
    const h: Mat3 = [1, 0, 0, 0, 1, 0, 0, 0, 2];
    expect(applyH(h, [10, 20])).toEqual([5, 10]);
  });
});

describe("mul3 / invert3", () => {
  it("M · M⁻¹ = identidade", () => {
    const m: Mat3 = [2, 0, 1, 0, 3, 2, 0, 0, 1];
    const inv = invert3(m);
    expect(inv).not.toBeNull();
    const result = mul3(m, inv!);
    result.forEach((v, i) => expect(v).toBeCloseTo(IDENTITY[i], 9));
  });

  it("matriz singular não tem inversa", () => {
    const singular: Mat3 = [1, 2, 3, 2, 4, 6, 1, 1, 1];
    expect(invert3(singular)).toBeNull();
  });
});

describe("rectQuad", () => {
  it("gera os 4 cantos na ordem TL, TR, BR, BL", () => {
    expect(rectQuad(10, 20, 100, 50)).toEqual([
      [10, 20],
      [110, 20],
      [110, 70],
      [10, 70],
    ]);
  });
});

describe("validateQuad", () => {
  const quadrado: Point[] = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
  ];

  it("aceita um quadrado simples (sem erro)", () => {
    expect(validateQuad(quadrado)).toBeNull();
  });

  it("recusa menos de 4 cantos", () => {
    expect(validateQuad(quadrado.slice(0, 3))).toMatch(/4 cantos/);
  });

  it("recusa coordenada não finita (NaN/Infinity)", () => {
    const comNaN: Point[] = [[0, 0], [10, 0], [10, NaN], [0, 10]];
    expect(validateQuad(comNaN)).toMatch(/inválidas/);
  });

  it("recusa quad degenerado (área ~0)", () => {
    const linha: Point[] = [[0, 0], [10, 0], [10, 0.0001], [0, 0.0001]];
    expect(validateQuad(linha)).toMatch(/degenerado/);
  });

  it("recusa quad côncavo (dardo, sem autointerseção) — mesmo erro que o servidor recusaria", () => {
    // Um dos 4 cantos empurrado pro centro: área não-zero, mas um vértice é reflexo.
    const concavo: Point[] = [
      [0, 0],
      [10, 0],
      [10, 10],
      [5, 3],
    ];
    expect(validateQuad(concavo)).toMatch(/côncavo ou cruzado/);
  });

  it("recusa quad autointersectante ('borboleta') — aqui a área líquida já dá zero, então cai em 'degenerado' antes de chegar à checagem de concavidade", () => {
    const borboleta: Point[] = [
      [0, 0],
      [10, 10],
      [10, 0],
      [0, 10],
    ];
    expect(validateQuad(borboleta)).toMatch(/degenerado/);
  });
});

describe("pointInQuad", () => {
  const quadrado: Point[] = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
  ];

  it("ponto no centro está dentro", () => {
    expect(pointInQuad([5, 5], quadrado)).toBe(true);
  });

  it("ponto bem fora está fora", () => {
    expect(pointInQuad([50, 50], quadrado)).toBe(false);
  });
});

describe("homography4", () => {
  it("mapeia os 4 cantos de origem exatamente nos 4 cantos de destino", () => {
    const src = rectQuad(0, 0, 100, 100);
    const dst: Point[] = [
      [20, 30],
      [220, 50],
      [200, 280],
      [10, 260],
    ]; // um quad arbitrário, não-retangular — testa a homografia de verdade, não só escala/translação
    const h = homography4(src, dst);
    expect(h).not.toBeNull();
    src.forEach((p, i) => {
      const mapped = applyH(h!, p);
      expect(mapped[0]).toBeCloseTo(dst[i][0], 6);
      expect(mapped[1]).toBeCloseTo(dst[i][1], 6);
    });
  });
});
