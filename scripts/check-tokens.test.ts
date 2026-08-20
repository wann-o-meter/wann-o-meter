import { describe, expect, it } from "vitest";
import { tokenViolations } from "./check-tokens.mjs";

describe("the scale", () => {
  it("is named nowhere but in tokens.css", () => {
    expect(tokenViolations()).toEqual([]);
  });
});
