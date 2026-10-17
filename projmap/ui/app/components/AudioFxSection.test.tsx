import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AudioFxSection from "./AudioFxSection";
import type { AudioFx } from "../lib/types";

const STROBE: AudioFx = { type: "strobe", band: "beat", amount: 0.8, enabled: true };

function setup(fx: AudioFx[] = []) {
  const onChange = vi.fn();
  render(<AudioFxSection fx={fx} onChange={onChange} />);
  return onChange;
}

describe("AudioFxSection", () => {
  it("sem efeitos mostra a dica e '+ Efeito' adiciona um pulse nos graves", async () => {
    const onChange = setup();
    expect(screen.getByText(/Nenhum efeito/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "+ Efeito" }));

    expect(onChange).toHaveBeenCalledWith([{ type: "pulse", band: "bass", amount: 0.5, enabled: true }]);
  });

  it("trocar o tipo do efeito chama onChange com o tipo novo", async () => {
    const onChange = setup([STROBE]);
    await userEvent.click(screen.getByLabelText("Efeito 1"));
    await userEvent.click(await screen.findByRole("option", { name: "Zoom" }));

    expect(onChange).toHaveBeenCalledWith([{ ...STROBE, type: "zoom" }]);
  });

  it("trocar a banda chama onChange com a banda nova", async () => {
    const onChange = setup([STROBE]);
    await userEvent.click(screen.getByLabelText("Reage a 1"));
    await userEvent.click(await screen.findByRole("option", { name: "Agudos" }));

    expect(onChange).toHaveBeenCalledWith([{ ...STROBE, band: "high" }]);
  });

  it("mover a intensidade pelo teclado chama onChange", async () => {
    const onChange = setup([STROBE]);
    const slider = screen.getByRole("slider", { name: "Intensidade 1" });
    slider.focus();
    await userEvent.keyboard("{ArrowLeft}");

    const next = onChange.mock.calls.at(-1)![0] as AudioFx[];
    expect(next[0].amount).toBeLessThan(0.8);
  });

  it("desligar e remover um efeito", async () => {
    const onChange = setup([STROBE, { ...STROBE, type: "pulse", band: "bass" }]);
    await userEvent.click(screen.getByRole("checkbox", { name: "Ligado 1" }));
    expect(onChange).toHaveBeenLastCalledWith([{ ...STROBE, enabled: false }, { ...STROBE, type: "pulse", band: "bass" }]);

    await userEvent.click(screen.getByRole("button", { name: "Remover efeito 2" }));
    expect(onChange).toHaveBeenLastCalledWith([STROBE]);
  });

  it("no máximo 8 efeitos: o botão some", () => {
    setup(Array.from({ length: 8 }, () => STROBE));
    expect(screen.queryByRole("button", { name: "+ Efeito" })).not.toBeInTheDocument();
  });
});
