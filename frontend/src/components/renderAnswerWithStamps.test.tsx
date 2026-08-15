import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAnswerWithStamps } from "./renderAnswerWithStamps";

describe("renderAnswerWithStamps", () => {
  it("splits plain text around citation markers into stamps", () => {
    const { container } = render(
      <div>{renderAnswerWithStamps("EPA spent $1B [award:068-FY2026] this year.")}</div>
    );
    expect(container.textContent).toBe("EPA spent $1B [award:068-FY2026] this year.");
    expect(container.querySelectorAll("span, a").length).toBeGreaterThanOrEqual(1);
  });

  it("handles text with no citations", () => {
    const { container } = render(<div>{renderAnswerWithStamps("Did you mean this year?")}</div>);
    expect(container.textContent).toBe("Did you mean this year?");
  });

  it("handles multiple citations", () => {
    const { container } = render(
      <div>{renderAnswerWithStamps("Two rules [doc:1] and [doc:2] apply.")}</div>
    );
    expect(container.textContent).toBe("Two rules [doc:1] and [doc:2] apply.");
  });
});
