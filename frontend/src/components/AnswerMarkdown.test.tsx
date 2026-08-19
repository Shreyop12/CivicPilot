import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerMarkdown } from "./AnswerMarkdown";

describe("AnswerMarkdown", () => {
  it("splits plain text around citation markers into stamps", () => {
    const { container } = render(<AnswerMarkdown text="EPA spent $1B [award:068-FY2026] this year." />);
    expect(container.textContent).toContain("EPA spent $1B");
    expect(container.textContent).toContain("[award:068-FY2026]");
    expect(container.textContent).toContain("this year.");
    expect(container.querySelectorAll("span, a").length).toBeGreaterThanOrEqual(1);
  });

  it("handles text with no citations", () => {
    const { container } = render(<AnswerMarkdown text="Did you mean this year?" />);
    expect(container.textContent).toContain("Did you mean this year?");
  });

  it("handles multiple citations", () => {
    const { container } = render(<AnswerMarkdown text="Two rules [doc:1] and [doc:2] apply." />);
    expect(container.textContent).toContain("Two rules");
    expect(container.textContent).toContain("[doc:1]");
    expect(container.textContent).toContain("[doc:2]");
  });

  it("renders a markdown table with real table elements", () => {
    const markdown = "| Date | Title |\n| --- | --- |\n| 30 Jun 2026 | Airworthiness Directives |";
    const { container } = render(<AnswerMarkdown text={markdown} />);
    expect(container.querySelector("table")).toBeInTheDocument();
    expect(container.querySelectorAll("th").length).toBe(2);
    expect(container.textContent).toContain("Airworthiness Directives");
  });

  it("renders bold text as a strong element, not literal asterisks", () => {
    const { container } = render(<AnswerMarkdown text="**DOT final rules** published recently." />);
    expect(container.querySelector("strong")).toBeInTheDocument();
    expect(container.textContent).not.toContain("**");
  });
});
