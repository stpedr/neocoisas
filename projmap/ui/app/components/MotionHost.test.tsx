import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MotionHost from "./MotionHost";

class FakeWS {
  static last: FakeWS | null = null;
  binaryType = "blob";
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: unknown[] = [];
  constructor(public url: string) {
    FakeWS.last = this;
  }
  send(d: unknown) {
    this.sent.push(d);
  }
  close() {}
}

describe("MotionHost", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", FakeWS);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, text: async () => "<html><head></head><body><canvas></canvas></body></html>" }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("liga no WebSocket do mestre e cria um iframe sandbox por sessão, do tamanho pedido", async () => {
    render(<MotionHost />);
    expect(FakeWS.last?.url).toMatch(/\/ws\/motion-host$/);
    expect(FakeWS.last?.binaryType).toBe("arraybuffer");

    await act(async () => {
      FakeWS.last!.onmessage!({
        data: JSON.stringify({
          type: "sessions",
          sessions: [{ sid: "m1", media: "abc", w: 640, h: 360, params: {}, mode: null, device: null }],
        }),
      });
    });

    const frame = await screen.findByTitle("motion m1");
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.getAttribute("srcdoc")).toContain("projmap:frame");
    expect(frame.style.width).toBe("640px");
    expect(frame.style.height).toBe("360px");
    expect(fetch).toHaveBeenCalledWith("/media/abc", expect.anything());
  });

  it("sessão removida some da página", async () => {
    render(<MotionHost />);
    const send = (sessions: unknown[]) =>
      act(async () => FakeWS.last!.onmessage!({ data: JSON.stringify({ type: "sessions", sessions }) }));
    await send([{ sid: "m1", media: "abc", w: 64, h: 64, params: {}, mode: null, device: null }]);
    expect(await screen.findByTitle("motion m1")).toBeInTheDocument();
    await send([]);
    expect(screen.queryByTitle("motion m1")).not.toBeInTheDocument();
  });
});
