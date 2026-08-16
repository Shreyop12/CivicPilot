import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAgencies, fetchDashboard, postChat } from "./client";

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

  it("postChat sends conversation_id and message as JSON", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ answer: "Fine.", dropped_claims: [], needs_clarification: false, clarification_question: null }),
    });

    await postChat("conv-1", "What did EPA spend?");

    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ conversation_id: "conv-1", message: "What did EPA spend?" });
  });

  it("throws when the response is not ok", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

    await expect(fetchAgencies()).rejects.toThrow();
  });
});
