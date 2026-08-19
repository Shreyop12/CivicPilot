import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAgencies, fetchDashboard, streamChat } from "./client";

function makeStreamBody(chunks: string[]) {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    getReader() {
      return {
        async read() {
          if (i < chunks.length) {
            const value = encoder.encode(chunks[i]);
            i += 1;
            return { done: false, value };
          }
          return { done: true, value: undefined };
        },
      };
    },
  };
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("api client", () => {
  it("fetchAgencies calls GET /api/agencies and returns parsed JSON", async () => {
    const agencies = [{ name: "EPA", toptier_code: "068", fr_slug: "environmental-protection-agency" }];
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => agencies,
    });

    const result = await fetchAgencies();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/agencies"),
      expect.objectContaining({}),
    );
    expect(result).toEqual(agencies);
  });

  it("fetchDashboard calls the agency-scoped dashboard route", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ name: "EPA" }),
    });

    await fetchDashboard("068");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/agencies/068/dashboard"),
      expect.objectContaining({}),
    );
  });

  it("throws when the response is not ok", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

    await expect(fetchAgencies()).rejects.toThrow();
  });

  it("streamChat posts to /api/chat/stream and parses SSE events split across chunk boundaries", async () => {
    const sse =
      'data: {"type":"status","tool":"search_federal_register","message":"Searching…"}\n\n' +
      'data: {"type":"answer","answer":"EPA spent $1B [award:1].","dropped_claims":[],"needs_clarification":false,"clarification_question":null}\n\n';
    const splitPoint = 30;
    const body = makeStreamBody([sse.slice(0, splitPoint), sse.slice(splitPoint)]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, body });

    const events: unknown[] = [];
    await streamChat("conv-1", "What did EPA spend?", (event) => events.push(event));

    expect(events).toEqual([
      { type: "status", tool: "search_federal_register", message: "Searching…" },
      {
        type: "answer", answer: "EPA spent $1B [award:1].", dropped_claims: [],
        needs_clarification: false, clarification_question: null,
      },
    ]);
    const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/api/chat/stream");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ conversation_id: "conv-1", message: "What did EPA spend?" });
  });

  it("streamChat throws when the response is not ok", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, status: 500, body: null });

    await expect(streamChat("conv-1", "hi", () => {})).rejects.toThrow();
  });
});
