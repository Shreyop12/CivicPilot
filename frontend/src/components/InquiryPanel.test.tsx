import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InquiryPanel } from "./InquiryPanel";
import { streamChat } from "../api/client";
import type { ChatStreamEvent } from "../api/types";

vi.mock("../api/client", () => ({
  streamChat: vi.fn(),
}));

function mockStream(events: ChatStreamEvent[]) {
  vi.mocked(streamChat).mockImplementation(async (_conversationId, _message, onEvent) => {
    for (const event of events) onEvent(event);
  });
}

describe("InquiryPanel", () => {
  it("sends a message on Enter and renders the cited answer", async () => {
    mockStream([
      { type: "answer", answer: "EPA spent $1B [award:068-FY2026].", dropped_claims: [], needs_clarification: false, clarification_question: null },
    ]);
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    expect(screen.getByText("What did EPA spend?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/EPA spent \$1B/)).toBeInTheDocument());
    expect(streamChat).toHaveBeenCalledWith("conv-1", "What did EPA spend?", expect.any(Function));
  });

  it("shows a dropped-claims caption when claims were omitted", async () => {
    mockStream([
      {
        type: "answer", answer: "EPA spent $1B [award:068-FY2026].",
        dropped_claims: ["unsupported claim one", "unsupported claim two"],
        needs_clarification: false, clarification_question: null,
      },
    ]);
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/2 unverifiable claims omitted/)).toBeInTheDocument());
  });

  it("renders a clarification response distinctly from a normal answer", async () => {
    mockStream([
      { type: "answer", answer: "", dropped_claims: [], needs_clarification: true, clarification_question: "Calendar year or fiscal year?" },
    ]);
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend this year?{Enter}");

    await waitFor(() => expect(screen.getByText("Calendar year or fiscal year?")).toBeInTheDocument());
  });

  it("shows a thinking indicator while a request is in flight", async () => {
    let resolveStream: () => void = () => {};
    vi.mocked(streamChat).mockReturnValue(
      new Promise((resolve) => {
        resolveStream = () => resolve(undefined);
      })
    );
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    expect(screen.getByText(/looking this up/i)).toBeInTheDocument();

    resolveStream();
    await waitFor(() => expect(screen.queryByText(/looking this up/i)).not.toBeInTheDocument());
  });

  it("shows the live status message from a status event, then replaces it with the final answer", async () => {
    let emitAnswer: () => void = () => {};
    vi.mocked(streamChat).mockImplementation(async (_conversationId, _message, onEvent) => {
      onEvent({ type: "status", tool: "search_federal_register", message: "Searching Federal Register…" });
      await new Promise<void>((resolve) => {
        emitAnswer = () => {
          onEvent({ type: "answer", answer: "EPA proposed one rule [doc:1].", dropped_claims: [], needs_clarification: false, clarification_question: null });
          resolve();
        };
      });
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA propose?{Enter}");

    await waitFor(() => expect(screen.getByText("Searching Federal Register…")).toBeInTheDocument());

    emitAnswer();
    await waitFor(() => expect(screen.getByText(/EPA proposed one rule/)).toBeInTheDocument());
    expect(screen.queryByText("Searching Federal Register…")).not.toBeInTheDocument();
  });

  it("shows an error bubble when the request fails", async () => {
    vi.mocked(streamChat).mockRejectedValue(new Error("network error"));
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
  });

  it("shows an error bubble when the stream itself yields an error event", async () => {
    mockStream([{ type: "error", detail: "Answer generation is temporarily unavailable — try again." }]);
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
  });
});
