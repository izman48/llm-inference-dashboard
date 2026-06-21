import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StrategySwitcher } from "./StrategySwitcher";

describe("StrategySwitcher", () => {
  it("lists strategies and reports a live switch", async () => {
    const onChange = vi.fn();
    render(
      <StrategySwitcher
        strategies={["round-robin", "least-queue-depth", "power-of-two-choices"]}
        current="round-robin"
        onChange={onChange}
      />,
    );
    const select = screen.getByLabelText("routing strategy");
    await userEvent.selectOptions(select, "power-of-two-choices");
    expect(onChange).toHaveBeenCalledWith("power-of-two-choices");
  });
});
