"""Telas (monitores/projetores) em ordem estável, e escolha automática do projetor.

O Windows não garante a ordem das telas: numa máquina real o projetor veio
como índice 0 e a tela do notebook como 1, então "monitor 1" caía no
notebook. Aqui a numeração é sempre:

    0 = tela principal (a que tem a barra de tarefas)
    1, 2… = as outras, da esquerda para a direita

e ``"auto"`` escolhe a primeira tela que **não** é a principal (o projetor,
com as telas em modo *Estender*). Com uma tela só, usa a principal.

    python -m projmap.node.screens     # lista as telas e qual o "auto" escolhe
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union


@dataclass(frozen=True)
class ScreenInfo:
    index: int  # na ordem estável (0 = principal)
    x: int
    y: int
    width: int
    height: int
    primary: bool
    handle: Any = None  # objeto de tela do pyglet

    @property
    def label(self) -> str:
        kind = "principal" if self.primary else "projetor/externa"
        return f"{self.index}: {self.width}x{self.height} ({kind})"


def order_screens(raw: list[tuple[int, int, int, int, Any]]) -> list[ScreenInfo]:
    """``raw`` = [(x, y, largura, altura, handle)]. A principal fica na origem (0, 0)."""
    if not raw:
        return []
    prim = next((r for r in raw if r[0] == 0 and r[1] == 0), raw[0])
    others = sorted((r for r in raw if r is not prim), key=lambda r: (r[0], r[1]))
    return [ScreenInfo(i, r[0], r[1], r[2], r[3], r is prim, r[4]) for i, r in enumerate([prim, *others])]


def list_screens() -> list[ScreenInfo]:
    import pyglet

    scr = pyglet.display.get_display().get_screens()
    return order_screens([(s.x, s.y, s.width, s.height, s) for s in scr])


def choose_screen(screens: list[ScreenInfo], want: Union[str, int, None] = "auto") -> Optional[ScreenInfo]:
    """``want``: "auto" (primeira não principal), "principal" ou o número da tela."""
    if not screens:
        return None
    w = str(want if want is not None else "auto").strip().lower()
    if w in ("auto", "projetor", ""):
        return next((s for s in screens if not s.primary), screens[0])
    if w in ("principal", "primary"):
        return screens[0]
    try:
        i = int(w)
    except ValueError:
        raise ValueError(f"tela inválida: {want!r} (use auto, principal ou um número)") from None
    return screens[i] if 0 <= i < len(screens) else None


if __name__ == "__main__":
    screens = list_screens()
    pick = choose_screen(screens, "auto")
    print("Telas:" if screens else "Nenhuma tela encontrada.")
    for s in screens:
        mark = "  <-- 'auto' usa esta" if pick and s.index == pick.index else ""
        print(f"  {s.label}  em ({s.x}, {s.y}){mark}")
    if len(screens) == 1:
        print("Só uma tela: ligue o projetor e use Windows+P -> Estender.")
