import { describe, expect, it } from "vitest";
import {
  dayNum,
  dow,
  isWeekend,
  isoOfDay,
  monthFirsts,
  monthWindow,
  packLanes,
} from "./timeline-geometry";

describe("day numbers", () => {
  it("round-trips an ISO day", () => {
    expect(isoOfDay(dayNum("2026-11-08"))).toBe("2026-11-08");
  });

  it("knows the weekday without a Date", () => {
    // 2026-11-08 is a Sunday, 2026-11-09 a Monday.
    expect(dow(dayNum("2026-11-08"))).toBe(0);
    expect(dow(dayNum("2026-11-09"))).toBe(1);
    expect(isWeekend(dayNum("2026-11-07"))).toBe(true);
    expect(isWeekend(dayNum("2026-11-09"))).toBe(false);
  });
});

describe("monthWindow", () => {
  it("widens to whole months so every month label has its column", () => {
    const w = monthWindow([dayNum("2026-08-10"), dayNum("2026-11-08")]);
    expect(isoOfDay(w.from)).toBe("2026-08-01");
    expect(isoOfDay(w.to)).toBe("2026-11-30");
  });

  it("keeps a single day inside its own month", () => {
    const w = monthWindow([dayNum("2027-02-15")]);
    expect(isoOfDay(w.from)).toBe("2027-02-01");
    expect(isoOfDay(w.to)).toBe("2027-02-28");
  });
});

describe("monthFirsts", () => {
  it("lists every month start in the window, year boundary included", () => {
    const from = dayNum("2026-11-01");
    const to = dayNum("2027-01-31");
    expect(monthFirsts(from, to).map(isoOfDay)).toEqual([
      "2026-11-01",
      "2026-12-01",
      "2027-01-01",
    ]);
  });
});

describe("packLanes", () => {
  it("keeps overlapping items apart and reuses a free lane", () => {
    const lanes = packLanes(
      [
        { left: 0, right: 100 },
        { left: 50, right: 150 }, // overlaps the first
        { left: 120, right: 200 }, // clears the first, still hits the second
      ],
      8,
    );
    expect(lanes).toEqual([0, 1, 0]);
  });

  it("honours the minimum gap between two neighbours", () => {
    expect(
      packLanes(
        [
          { left: 0, right: 10 },
          { left: 14, right: 20 },
        ],
        8,
      ),
    ) //
      .toEqual([0, 1]);
    expect(
      packLanes(
        [
          { left: 0, right: 10 },
          { left: 20, right: 30 },
        ],
        8,
      ),
    ).toEqual([0, 0]);
  });
});
