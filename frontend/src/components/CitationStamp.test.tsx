import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CitationStamp } from "./CitationStamp";

describe("CitationStamp", () => {
  it("renders a verified citation as a bracketed label", () => {
    render(<CitationStamp label="doc:2026-1" variant="verified" />);
    expect(screen.getByText("[doc:2026-1]")).toBeInTheDocument();
  });

  it("renders as a link when href is provided", () => {
    render(<CitationStamp label="doc:2026-1" variant="verified" href="https://example.com/doc" />);
    expect(screen.getByRole("link", { name: "[doc:2026-1]" })).toHaveAttribute(
      "href", "https://example.com/doc",
    );
  });

  it("renders as plain text (no link) when href is omitted", () => {
    render(<CitationStamp label="award:068-FY2026" variant="verified" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders the unverified variant without brackets", () => {
    render(<CitationStamp label="UNVERIFIED MATCH" variant="unverified" />);
    expect(screen.getByText("UNVERIFIED MATCH")).toBeInTheDocument();
  });
});
