import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ColorControls, { cssFilter, isNeutral } from "./ColorControls";
import { DEFAULT_COLOR, type ColorAdjust } from "../lib/types";

describe("ColorControls", () => {
  it("renderiza um slider por campo (5 no modo completo)", () => {
    render(<ColorControls value={DEFAULT_COLOR} onChange={() => {}} />);
    expect(screen.getAllByRole("slider")).toHaveLength(5);
    expect(screen.getByRole("slider", { name: /Brilho/ })).toBeInTheDocument();
  });

  it("modo compact esconde Contraste e Temperatura (3 sliders)", () => {
    render(<ColorControls value={DEFAULT_COLOR} onChange={() => {}} compact />);
    expect(screen.getAllByRole("slider")).toHaveLength(3);
    expect(screen.queryByRole("slider", { name: /Contraste/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: /Temperatura/ })).not.toBeInTheDocument();
  });

  it("mover o slider de Brilho pelo teclado chama onChange com o brilho atualizado e o resto intacto", async () => {
    const onChange = vi.fn();
    render(<ColorControls value={DEFAULT_COLOR} onChange={onChange} />);
    const brilho = screen.getByRole("slider", { name: /Brilho/ });
    brilho.focus();
    await userEvent.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as ColorAdjust;
    expect(next.brightness).toBeGreaterThan(DEFAULT_COLOR.brightness);
    expect(next.gamma).toBe(DEFAULT_COLOR.gamma);
    expect(next.contrast).toBe(DEFAULT_COLOR.contrast);
    expect(next.saturation).toBe(DEFAULT_COLOR.saturation);
    expect(next.temperature).toBe(DEFAULT_COLOR.temperature);
  });

  it("duplo clique no controle reseta aquele campo para o padrão", async () => {
    const onChange = vi.fn();
    const valorAjustado: ColorAdjust = { ...DEFAULT_COLOR, brightness: 1.4 };
    render(<ColorControls value={valorAjustado} onChange={onChange} />);
    const brilho = screen.getByRole("slider", { name: /Brilho/ });
    await userEvent.dblClick(brilho);

    expect(onChange).toHaveBeenCalledWith({ ...valorAjustado, brightness: DEFAULT_COLOR.brightness });
  });
});

describe("isNeutral", () => {
  it("é neutro quando igual ao padrão", () => {
    expect(isNeutral(DEFAULT_COLOR)).toBe(true);
  });

  it("não é neutro com qualquer campo alterado", () => {
    expect(isNeutral({ ...DEFAULT_COLOR, saturation: 1.5 })).toBe(false);
  });
});

describe("cssFilter", () => {
  it("padrão produz brightness/contrast/saturate neutros (1.000)", () => {
    expect(cssFilter(DEFAULT_COLOR)).toBe("brightness(1.000) contrast(1.000) saturate(1.000)");
  });

  it("temperatura positiva (quente) soma sepia()", () => {
    expect(cssFilter({ ...DEFAULT_COLOR, temperature: 0.4 })).toContain("sepia(");
  });

  it("temperatura negativa (fria) soma hue-rotate()", () => {
    expect(cssFilter({ ...DEFAULT_COLOR, temperature: -0.4 })).toContain("hue-rotate(");
  });
});
