// The calendar's URL contract, as pure functions: query string -> state and
// state -> query string. Split out of Kalender.vue so the rules (which
// param wins, what a malformed value falls back to) are testable without a
// browser or a mounted component - the component keeps the reactive refs
// and just calls these two.
import { isoFromDate, mondayOf } from "./date-grid";

// ponytail: no data-driven lower bound is known (holiday/vacation data goes
// back further than any constant here could track) - 1900 is just a sane
// floor so the typed-year input can validate against something.
export const YEAR_MIN = 1900;
export const YEAR_MAX = new Date().getFullYear() + 5;

// Every value here is a render template over the same layer data, not a
// different dataset - adding one means a new component in
// src/components/calendar/ plus an entry in this union.
export type CalendarView = "year" | "month" | "week" | "planner" | "graph";

// Month-scoped templates: the ones whose URL has to carry month= to be a
// meaningful deep link.
const MONTH_SCOPED: CalendarView[] = ["month", "week", "planner"];

export interface CalendarState {
  year: number;
  view: CalendarView;
  monthIndex0: number;
  weekStartIso: string;
  selectedDay: string | null;
  layerIds: string[];
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function parseIsoDay(value: string | null): Date | null {
  if (!value || !ISO_DAY.test(value)) return null;
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function isCalendarView(value: unknown): value is CalendarView {
  return (
    value === "year" || value === "month" || value === "week" || value === "planner" || value === "graph"
  );
}

// Returns a COMPLETE state, not a patch - every field is resolved from the
// URL or from a fallback, so this is safe to call both on mount and again on
// popstate, where a previous, differently-shaped URL has to fully replace
// the current state rather than merely amend it.
//
// `fallbackView` is where the stored preference goes: an explicit view= in
// the URL always wins over it, and it in turn wins over "year".
export function parseCalendarUrl(search: string, today: Date, fallbackView: CalendarView = "year"): CalendarState {
  const params = new URLSearchParams(search);

  const y = Number(params.get("year"));
  let year = y >= YEAR_MIN && y <= YEAR_MAX ? y : today.getFullYear();

  const viewParam = params.get("view");
  let view: CalendarView = isCalendarView(viewParam) ? viewParam : fallbackView;

  // 1-indexed in the URL (month=3 -> March) even though monthIndex0 is
  // 0-indexed internally (JS Date convention) - a raw 0-index would read as
  // April to anyone reading/writing the URL by hand.
  const monthParam = Number(params.get("month"));
  let monthIndex0 = monthParam >= 1 && monthParam <= 12 ? monthParam - 1 : today.getMonth();

  // Snapped to its own Monday rather than taken verbatim - a hand-edited URL
  // can put any date here, including one that isn't a Monday at all.
  const parsedWeekStart = parseIsoDay(params.get("weekstart"));
  let weekStartIso = isoFromDate(mondayOf(parsedWeekStart ?? today));

  // weekstart is the only value week view actually renders from, so once
  // it's the active view it's treated as the sole source of truth for
  // year/month too, overriding whatever they say - otherwise a hand-edited
  // URL with a mismatched month= (or year=) produces a breadcrumb that
  // contradicts the days actually shown.
  if (view === "week" && parsedWeekStart) {
    const monday = mondayOf(parsedWeekStart);
    year = monday.getFullYear();
    monthIndex0 = monday.getMonth();
  }

  // A data page's date link ("open the calendar on this exact day") - takes
  // priority over year/view/weekstart above, which is why it's applied
  // after them instead of merged into their fallback logic.
  const day = parseIsoDay(params.get("day"));
  let selectedDay: string | null = null;
  if (day) {
    selectedDay = isoFromDate(day);
    view = "week";
    weekStartIso = isoFromDate(mondayOf(day));
    year = day.getFullYear();
    monthIndex0 = mondayOf(day).getMonth();
  }

  return {
    year,
    view,
    monthIndex0,
    weekStartIso,
    selectedDay,
    layerIds: params.get("layers")?.split(",").filter(Boolean) ?? [],
  };
}

// Shared by the page's own address bar and by the /kalender/embed/ link,
// which need the same "what does the current view look like" query string -
// `live` is what differs: concrete current values for a link to exactly this
// moment, the literal string "current" for an embed, whose values then fail
// to parse above and fall back to today (so an embedded widget always shows
// "now" instead of freezing at whatever date the embed link was copied on).
//
// Only what the active view actually renders from is serialized: a year-view
// URL carries no month=, so parsing it back yields today's month, not the
// one that happened to be in state.
export function buildCalendarParams(state: CalendarState, live: boolean): URLSearchParams {
  const params = new URLSearchParams();
  params.set("year", live ? "current" : String(state.year));
  if (state.view !== "year") params.set("view", state.view);
  if (MONTH_SCOPED.includes(state.view)) {
    params.set("month", live ? "current" : String(state.monthIndex0 + 1));
  }
  if (state.view === "week") params.set("weekstart", live ? "current" : state.weekStartIso);
  if (state.layerIds.length) params.set("layers", state.layerIds.join(","));
  return params;
}
