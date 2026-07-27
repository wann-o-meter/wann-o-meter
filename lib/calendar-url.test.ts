import { describe, expect, it } from "vitest";
import { type CalendarState, DEFAULT_VIEW, buildCalendarParams, parseCalendarUrl } from "./calendar-url";

const TODAY = new Date("2026-07-26T00:00:00"); // a Sunday
const THIS_MONDAY = "2026-07-20";

describe("parseCalendarUrl", () => {
  it("falls back to today for an empty query", () => {
    expect(parseCalendarUrl("", TODAY)).toEqual({
      year: 2026,
      view: DEFAULT_VIEW,
      monthIndex0: 6,
      weekStartIso: THIS_MONDAY,
      selectedDay: null,
      layerIds: [],
    });
  });

  it("uses the stored view only when the URL names none", () => {
    expect(parseCalendarUrl("", TODAY, "month").view).toBe("month");
    expect(parseCalendarUrl("?view=week", TODAY, "month").view).toBe("week");
    // An explicit view=year has to survive a stored preference, or the
    // switcher could never be used to get back to the year template.
    expect(parseCalendarUrl("?view=year", TODAY, "month").view).toBe("year");
    expect(parseCalendarUrl("?view=nonsense", TODAY, "month").view).toBe("month");
  });

  it("rejects out-of-range and malformed values", () => {
    expect(parseCalendarUrl("?year=1500", TODAY).year).toBe(2026);
    expect(parseCalendarUrl("?year=current", TODAY).year).toBe(2026);
    expect(parseCalendarUrl("?month=13", TODAY).monthIndex0).toBe(6);
    expect(parseCalendarUrl("?month=3", TODAY).monthIndex0).toBe(2);
    expect(parseCalendarUrl("?view=week&weekstart=heute", TODAY).weekStartIso).toBe(THIS_MONDAY);
    expect(parseCalendarUrl("?view=week&weekstart=2026-13-45", TODAY).weekStartIso).toBe(THIS_MONDAY);
    // ponytail: an in-format but nonexistent date rolls over the way Date
    // does (Feb 30 -> Mar 2) instead of being rejected - it still renders a
    // real week, and writeUrl canonicalizes the address bar right after.
    expect(parseCalendarUrl("?view=week&weekstart=2026-02-30", TODAY).weekStartIso).toBe("2026-03-02");
  });

  it("snaps weekstart to its Monday and lets it override year/month", () => {
    const state = parseCalendarUrl("?year=2020&month=1&view=week&weekstart=2026-09-03", TODAY);
    expect(state.weekStartIso).toBe("2026-08-31");
    expect(state.year).toBe(2026);
    expect(state.monthIndex0).toBe(7);
  });

  it("lets day= win over everything else", () => {
    const state = parseCalendarUrl("?view=year&year=2020&day=2026-09-03", TODAY);
    expect(state).toMatchObject({
      view: "week",
      selectedDay: "2026-09-03",
      weekStartIso: "2026-08-31",
      year: 2026,
      monthIndex0: 7,
    });
  });

  it("reads layers as a comma list, ignoring empties", () => {
    expect(parseCalendarUrl("?layers=a,,b", TODAY).layerIds).toEqual(["a", "b"]);
    expect(parseCalendarUrl("?layers=", TODAY).layerIds).toEqual([]);
  });
});

describe("state -> URL -> state", () => {
  const roundTrip = (state: CalendarState) =>
    parseCalendarUrl(`?${buildCalendarParams(state, false)}`, TODAY);

  it("preserves everything a week-view URL carries", () => {
    const state: CalendarState = {
      year: 2027,
      view: "week",
      monthIndex0: 8,
      weekStartIso: "2027-09-06",
      selectedDay: null,
      layerIds: ["feiertage--bayern", "ferien--nrw"],
    };
    expect(roundTrip(state)).toEqual(state);
  });

  it("preserves everything a month-view URL carries", () => {
    const state: CalendarState = {
      year: 2027,
      view: "month",
      monthIndex0: 8,
      weekStartIso: THIS_MONDAY,
      selectedDay: null,
      layerIds: [],
    };
    // Month is DEFAULT_VIEW, so it is the one view omitted from the URL - the
    // round trip below is what proves the omitted value and the parse fallback
    // are still the same view.
    expect(buildCalendarParams(state, false).has("view")).toBe(false);
    expect(roundTrip(state)).toEqual(state);
  });

  it("carries the month for the planner too, which is month-scoped", () => {
    const state: CalendarState = {
      year: 2027,
      view: "planner",
      monthIndex0: 8,
      weekStartIso: THIS_MONDAY,
      selectedDay: null,
      layerIds: ["ferien--by"],
    };
    expect(buildCalendarParams(state, false).get("month")).toBe("9");
    expect(roundTrip(state)).toEqual(state);
  });

  it("drops what the active view does not render from", () => {
    // Year view serializes no month=/weekstart=, by design - so those come
    // back as today's, not as whatever they happened to be in state.
    const back = roundTrip({
      year: 2027,
      view: "year",
      monthIndex0: 8,
      weekStartIso: "2027-09-06",
      selectedDay: null,
      layerIds: [],
    });
    expect(back).toMatchObject({ year: 2027, view: "year", monthIndex0: 6, weekStartIso: THIS_MONDAY });
  });

  it("builds an embed URL that always resolves to now", () => {
    const params = buildCalendarParams(
      { year: 2020, view: "week", monthIndex0: 0, weekStartIso: "2020-01-06", selectedDay: null, layerIds: ["x"] },
      true,
    );
    expect(params.get("year")).toBe("current");
    expect(params.get("weekstart")).toBe("current");
    expect(parseCalendarUrl(`?${params}`, TODAY)).toMatchObject({
      year: 2026,
      view: "week",
      weekStartIso: THIS_MONDAY,
      layerIds: ["x"],
    });
  });
});
