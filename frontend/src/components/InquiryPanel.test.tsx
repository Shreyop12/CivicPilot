import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InquiryPanel } from "./InquiryPanel";
import { postChat } from "../api/client";
import type { ChatResponse } from "../api/types";

vi.mock("../api/client", () => ({
  postChat: vi.fn(),
}));

describe("InquiryPanel", () => {
  it("sends a message on Enter and renders the cited answer", async () => {
    vi.mocked(postChat).mockResolvedValue({
      answer: "EPA spent $1B [award:068-FY2026].",
      dropped_claims: [],
      needs_clarification: false,
      clarification_question: null,
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    expect(screen.getByText("What did EPA spend?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/EPA spent \$1B/)).toBeInTheDocument());
    expect(postChat).toHaveBeenCalledWith("conv-1", "What did EPA spend?");
  });

  it("shows a dropped-claims caption when claims were omitted", async () => {
    vi.mocked(postChat).mockResolvedValue({
      answer: "EPA spent $1B [award:068-FY2026].",
      dropped_claims: ["unsupported claim one", "unsupported claim two"],
      needs_clarification: false,
      clarification_question: null,
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/2 unverifiable claims omitted/)).toBeInTheDocument());
  });

  it("renders a clarification response distinctly from a normal answer", async () => {
    vi.mocked(postChat).mockResolvedValue({
      answer: "",
      dropped_claims: [],
      needs_clarification: true,
      clarification_question: "Calendar year or fiscal year?",
    });
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend this year?{Enter}");

    await waitFor(() => expect(screen.getByText("Calendar year or fiscal year?")).toBeInTheDocument());
  });

  it("shows a thinking indicator while a request is in flight", async () => {
    let resolveChat: (value: ChatResponse) => void = () => {};
    vi.mocked(postChat).mockReturnValue(
      new Promise((resolve) => {
        resolveChat = resolve;
      })
    );
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    expect(screen.getByText(/looking this up/i)).toBeInTheDocument();

    resolveChat({
      answer: "EPA spent $1B [award:068-FY2026].",
      dropped_claims: [],
      needs_clarification: false,
      clarification_question: null,
    });
    await waitFor(() => expect(screen.queryByText(/looking this up/i)).not.toBeInTheDocument());
  });

  it("shows an error bubble when the request fails", async () => {
    vi.mocked(postChat).mockRejectedValue(new Error("network error"));
    render(<InquiryPanel conversationId="conv-1" />);

    await userEvent.type(screen.getByLabelText(/ask a follow-up/i), "What did EPA spend?{Enter}");

    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
  });
});
