import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// RTL faz cleanup automático só se detectar um `afterEach` global; como não
// ligamos `test.globals` no vitest.config, registramos explicitamente —
// senão o DOM de um teste vaza pro próximo (ex.: "multiple elements found"
// quando dois `render()` da mesma suíte deixam sliders duplicados no body).
afterEach(() => cleanup());

// jsdom não implementa ResizeObserver; componentes Radix (ex.: Slider, via
// useSize) dependem dele pra medir o próprio tamanho. Polyfill mínimo — só
// o suficiente pra não quebrar o render em teste, não mede nada de verdade.
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// @ts-expect-error — jsdom não declara o tipo global
globalThis.ResizeObserver ??= ResizeObserverPolyfill;

// jsdom também não implementa a Pointer Capture API — Radix (Slider, Dialog
// etc.) chama isso em resposta a pointerdown/dblclick. Sem o stub, sobe
// "target.setPointerCapture is not a function" como exceção não capturada
// a cada interação simulada por @testing-library/user-event.
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};

// jsdom também não implementa scrollIntoView — Radix Select chama isso ao
// abrir, pra rolar até o item selecionado.
Element.prototype.scrollIntoView ??= () => {};
