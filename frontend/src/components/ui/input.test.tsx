import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Input } from "./input";

describe("Input", () => {
  it("accepts typed input", async () => {
    render(<Input aria-label="Search agencies" />);
    const input = screen.getByLabelText("Search agencies");

    await userEvent.type(input, "Energy");

    expect(input).toHaveValue("Energy");
  });
});
