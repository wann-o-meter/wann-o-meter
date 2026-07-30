import { describe, expect, it } from "vitest";
import { buildYearGrid, shouldRenderYearGrid, YEAR_GRID_MIN_DAYS } from "./year-grid";

describe("buildYearGrid", () => {
  it("returns 12 months of 31 cells each", () => {
    const grid = buildYearGrid(2026, []);
    expect(grid).toHaveLength(12);
    for (const month of grid) expect(month.cells).toHaveLength(31);
  });

  it("marks days past a month's length as empty", () => {
    const grid = buildYearGrid(2026, []); // 2026 is not a leap year
    const feb = grid[1];
    expect(feb.cells[27].state).not.toBe("empty"); // Feb 28
    expect(feb.cells[28].state).toBe("empty"); // Feb 29
    expect(feb.cells[28].iso).toBe("");
  });

  it("marks Saturdays and Sundays as weekend when no event lands there", () => {
    const grid = buildYearGrid(2026, []);
    const jan = grid[0];
    // 2026-01-03 is a Saturday, 2026-01-04 a Sunday.
    expect(jan.cells[2].state).toBe("weekend");
    expect(jan.cells[3].state).toBe("weekend");
    expect(jan.cells[0].state).toBe("plain"); // 2026-01-01 is a Thursday
  });

  it("marks a single-day event and carries its label", () => {
    const grid = buildYearGrid(2026, [{ date: "2026-01-01", label: "Neujahr" }]);
    const cell = grid[0].cells[0];
    expect(cell.state).toBe("event");
    expect(cell.titles).toEqual(["Neujahr"]);
  });

  it("fills every day of a multi-day range, event beats weekend", () => {
    const grid = buildYearGrid(2026, [{ date: "2026-01-02", to: "2026-01-05", label: "Ferien" }]);
    const jan = grid[0];
    for (let i = 1; i <= 4; i++) expect(jan.cells[i].state).toBe("event"); // Jan 2-5, incl. the weekend inside it
    expect(jan.cells[5].state).toBe("plain"); // Jan 6, first day after the range
  });

  it("clamps a range crossing the year boundary to the requested year", () => {
    const grid = buildYearGrid(2026, [{ date: "2025-12-23", to: "2026-01-06", label: "Weihnachtsferien" }]);
    expect(grid[11].cells[22].state).toBe("plain"); // Dec 23 2026 is untouched, the event was Dec 2025
    expect(grid[0].cells[5].state).toBe("event"); // Jan 6 2026, last day in range
    expect(grid[0].cells[6].state).toBe("plain"); // Jan 7 2026, first day after the range
  });
});

describe("shouldRenderYearGrid", () => {
  it("is false below the minimum covered days", () => {
    const events = Array.from({ length: YEAR_GRID_MIN_DAYS - 1 }, (_, i) => ({
      date: `2026-01-0${i + 1}`,
      label: "x",
    }));
    expect(shouldRenderYearGrid(buildYearGrid(2026, events))).toBe(false);
  });

  it("is true at or above the minimum covered days from point events", () => {
    const events = Array.from({ length: YEAR_GRID_MIN_DAYS }, (_, i) => ({
      date: `2026-01-${String(i + 1).padStart(2, "0")}`,
      label: "x",
    }));
    expect(shouldRenderYearGrid(buildYearGrid(2026, events))).toBe(true);
  });

  it("is true for a handful of multi-week ranges (Schulferien shape) even with few entries", () => {
    // 6 windows, like a real Schulferien year, but each one spans weeks.
    const events = [
      { date: "2026-01-05", to: "2026-01-16", label: "Weihnachtsferien" },
      { date: "2026-03-30", to: "2026-04-11", label: "Osterferien" },
      { date: "2026-05-26", to: "2026-05-29", label: "Pfingstferien" },
      { date: "2026-07-30", to: "2026-09-12", label: "Sommerferien" },
      { date: "2026-10-26", to: "2026-10-30", label: "Herbstferien" },
      { date: "2026-12-23", to: "2026-12-31", label: "Weihnachtsferien" },
    ];
    expect(events.length).toBeLessThan(YEAR_GRID_MIN_DAYS);
    expect(shouldRenderYearGrid(buildYearGrid(2026, events))).toBe(true);
  });
});
