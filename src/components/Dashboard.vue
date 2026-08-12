<script setup lang="ts">
import { computed, ref } from "vue";
import { computeSchedule } from "../../lib/deadline-plan";
import type { ScheduleEntry } from "../../lib/deadline-plan";
import { dayMonth, monthLabel, shortDate } from "../../lib/date-display";
import { isoToday } from "../../lib/today";
import { dayNum, isoOfDay } from "../../lib/timeline-geometry";
import { downloadIcs } from "../../lib/ics-download";
import {
  planStorageKey,
  readSnapshot,
  snapshotDeadlines,
} from "../../lib/saved-plans";
import type { SavedPlan } from "../../lib/saved-plans";
import type { VorhabenData } from "../../lib/vorhaben-data";
import TaskDates from "./deadline-planner/TaskDates.vue";
import { taskCtaFor } from "./deadline-planner/task-cta";

const props = defineProps<{
  vorhaben: VorhabenData[];
  plans: SavedPlan[];
}>();

defineEmits<{ (e: "forget", slug: string): void }>();

interface PlanView {
  plan: SavedPlan;
  v: VorhabenData;
  variantLabel: string;
  entries: ScheduleEntry[];
  done: Record<string, boolean>;
  href: string;
}

const TODAY = dayNum(isoToday());
const THIS_YEAR = new Date(TODAY * 86400000).getUTCFullYear();

const views = computed<PlanView[]>(() =>
  props.plans.flatMap((plan) => {
    const v = props.vorhaben.find((x) => x.slug === plan.slug);
    if (!v) return [];
    const variant =
      v.variants.find((x) => x.slug === plan.variant) ?? v.variants[0];
    const snap = readSnapshot(planStorageKey(v.vorhaben, variant.slug));
    const entries = computeSchedule(
      plan.date,
      snapshotDeadlines(variant.deadlines, snap),
      "DE",
      variant.regionCode,
    ).filter((e) => e.date !== null);
    return [
      {
        plan,
        v,
        variantLabel: v.variants.length > 1 ? variant.label : "",
        entries,
        done: snap.done,
        href: `/${v.slug}/${v.variants.length > 1 ? `${variant.slug}/` : ""}?date=${plan.date}`,
      },
    ];
  }),
);

const focusSlug = ref<string | null>(null);
const focus = computed<PlanView | undefined>(() => {
  const picked = views.value.find((v) => v.plan.slug === focusSlug.value);
  if (picked) return picked;
  const upcoming = views.value.filter((v) => dayNum(v.plan.date) >= TODAY);
  return (upcoming.length > 0 ? upcoming : views.value).reduce<
    PlanView | undefined
  >((best, v) => {
    if (!best) return v;
    return Math.abs(dayNum(v.plan.date) - TODAY) <
      Math.abs(dayNum(best.plan.date) - TODAY)
      ? v
      : best;
  }, undefined);
});

const openEntries = computed(() =>
  focus.value ? focus.value.entries.filter((e) => !focus.value!.done[e.id]) : [],
);
const overdue = computed(() =>
  openEntries.value.filter((e) => dayNum(e.date!) < TODAY),
);

// One card carries the most urgent open task, the list below is everything else.
const nowDue = computed(() => overdue.value[0] ?? openEntries.value[0] ?? null);
const rest = computed(() =>
  openEntries.value.filter((e) => e.id !== nowDue.value?.id),
);

const groups = computed(() => {
  const thisMonth = isoToday().slice(0, 7);
  const late = rest.value.filter((e) => dayNum(e.date!) < TODAY);
  const out: { key: string; title: string; entries: ScheduleEntry[] }[] = [];
  if (late.length > 0)
    out.push({ key: "late", title: "Überfällig", entries: late });
  out.push({
    key: thisMonth,
    title: "Diesen Monat",
    entries: rest.value.filter(
      (e) => dayNum(e.date!) >= TODAY && e.date!.slice(0, 7) === thisMonth,
    ),
  });
  for (const entry of rest.value) {
    const month = entry.date!.slice(0, 7);
    if (dayNum(entry.date!) < TODAY || month === thisMonth) continue;
    const group = out.find((g) => g.key === month);
    if (group) group.entries.push(entry);
    else
      out.push({
        key: month,
        title: `Im ${monthLabel(entry.date!, THIS_YEAR)}`,
        entries: [entry],
      });
  }
  return out;
});

const countdown = computed(() => {
  if (!focus.value) return "";
  const days = dayNum(focus.value.plan.date) - TODAY;
  if (days === 0) return "Heute";
  const n = Math.abs(days);
  const span =
    n < 14
      ? `${n} ${n === 1 ? "Tag" : "Tagen"}`
      : `${Math.round(n / 7)} Wochen`;
  return days > 0 ? `Noch ${span}` : `Vor ${span}`;
});

const progress = computed(() => {
  const entries = focus.value?.entries ?? [];
  const done = entries.filter((e) => focus.value!.done[e.id]).length;
  return {
    done,
    total: entries.length,
    pct: entries.length === 0 ? 0 : Math.round((done / entries.length) * 100),
  };
});

const collisions = computed(() => {
  const week = (day: number) => Math.floor((day + 3) / 7);
  const byWeek = new Map<number, { label: string; entry: ScheduleEntry }[]>();
  for (const view of views.value)
    for (const entry of view.entries) {
      const day = dayNum(entry.date!);
      if (view.done[entry.id] || day < TODAY) continue;
      const key = week(day);
      byWeek.set(key, [
        ...(byWeek.get(key) ?? []),
        { label: view.v.label, entry },
      ]);
    }
  return [...byWeek.entries()]
    .filter(([, list]) => new Set(list.map((i) => i.label)).size > 1)
    .sort(([a], [b]) => a - b)
    .map(([key, list]) => ({
      from: key * 7 - 3,
      labels: [...new Set(list.map((i) => i.label))].join(" und "),
      titles: list.map((i) => i.entry.label).join(", "),
    }));
});

function taskHref(view: PlanView, entry: ScheduleEntry): string {
  return `${view.href}#task-${entry.id}`;
}

function exportIcs(view: PlanView) {
  downloadIcs(
    view.entries,
    `${view.v.vorhaben} - ${view.variantLabel || "Bundesweit"}`,
    view.v.slug,
    view.plan.date,
  );
}
</script>

<template>
  <section v-if="focus" class="dashboard">
    <nav v-if="views.length > 1" class="switch" aria-label="Vorhaben">
      <button
        v-for="view in views"
        :key="view.plan.slug"
        type="button"
        :aria-current="view.plan.slug === focus.plan.slug ? 'true' : undefined"
        @click="focusSlug = view.plan.slug"
      >
        {{ view.v.label }}
      </button>
    </nav>

    <div v-for="(c, i) in collisions.slice(0, 2)" :key="i" class="collide">
      In der Woche ab {{ shortDate(isoOfDay(c.from)) }} treffen Fristen aus
      {{ c.labels }} zusammen: {{ c.titles }}.
    </div>

    <div class="split">
      <div class="main">
        <header class="hero">
          <h1>
            {{ focus.v.possessive }} {{ focus.v.label
            }}<template v-if="focus.variantLabel">
              · {{ focus.variantLabel }}</template
            >
          </h1>
          <p class="count">
            <span class="days">{{ countdown }}</span>
            <span class="mono">{{ shortDate(focus.plan.date) }}</span>
          </p>
          <div class="bar" aria-hidden="true">
            <i :style="{ width: progress.pct + '%' }"></i>
          </div>
          <p class="tally">
            {{ progress.done }} von {{ progress.total }} Fristen erledigt<template
              v-if="overdue.length > 0"
            >
              · {{ overdue.length }} überfällig</template
            >
          </p>
        </header>

        <template v-if="nowDue">
          <h2 class="group-title">Jetzt dran</h2>
          <article class="due">
            <a class="due-head" :href="taskHref(focus, nowDue)">
              <span class="check" aria-hidden="true"></span>
              <span class="due-label">{{ nowDue.label }}</span>
              <span
                v-if="dayNum(nowDue.date!) < TODAY"
                class="badge late"
                >Überfällig</span
              >
            </a>
            <TaskDates
              :entry="nowDue"
              :is-past="dayNum(nowDue.date!) < TODAY"
              :done="false"
              :show-rescue-label="true"
            />
            <a
              v-if="taskCtaFor(nowDue.id)"
              class="due-cta"
              :href="taskHref(focus, nowDue)"
            >
              {{ taskCtaFor(nowDue.id)!.label }} aufsetzen
            </a>
          </article>
        </template>

        <div v-for="group in groups" :key="group.key" class="group">
          <h2 class="group-title">{{ group.title }}</h2>
          <p v-if="group.entries.length === 0" class="empty">Nichts zu tun.</p>
          <a
            v-for="entry in group.entries"
            :key="entry.id"
            class="row"
            :href="taskHref(focus, entry)"
          >
            <span class="what">{{ entry.label }}</span>
            <span class="when mono">{{ dayMonth(entry.date!) }}</span>
          </a>
        </div>

        <p class="plan-actions">
          <a class="btn" :href="focus.href">Vollständigen Zeitplan öffnen</a>
          <button type="button" class="link" @click="exportIcs(focus)">
            Als Kalender exportieren
          </button>
        </p>
      </div>

      <aside class="cards">
        <article
          v-for="view in views"
          :key="view.plan.slug"
          class="card"
          :class="{ active: view.plan.slug === focus.plan.slug }"
        >
          <button type="button" class="card-pick" @click="focusSlug = view.plan.slug">
            {{ view.v.label }}
          </button>
          <p class="date mono">
            {{ shortDate(view.plan.date)
            }}<template v-if="view.variantLabel">
              · {{ view.variantLabel }}</template
            >
          </p>
          <p class="links">
            <a :href="view.href">Zeitplan</a>
            <button type="button" @click="$emit('forget', view.plan.slug)">
              Entfernen
            </button>
          </p>
        </article>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.dashboard {
  margin-bottom: 3rem;
}

/* Tabs, not pills: the picker below owns the pill shape for its inputs. */
.switch {
  display: flex;
  flex-wrap: wrap;
  gap: 1.2rem;
  border-bottom: 1px solid var(--line);
  margin-bottom: 1.5rem;
}
.switch button {
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  border-radius: 0;
  padding: 0 0 0.5rem;
  margin-bottom: -1px;
  color: var(--muted);
  font-size: var(--fs-sm);
  cursor: pointer;
}
.switch button:hover {
  color: var(--accent);
}
.switch button[aria-current] {
  border-bottom-color: var(--accent);
  color: var(--ink);
  font-weight: 600;
}

.collide {
  margin-bottom: 1rem;
  border-left: 3px solid var(--warn);
  background: color-mix(in srgb, var(--warn) 8%, transparent);
  padding: 0.6rem 0.9rem;
  font-size: var(--fs-sm);
}

.hero {
  margin-bottom: 1.75rem;
}
.hero h1 {
  margin: 0 0 0.4rem;
  font-size: var(--fs-sm);
  font-weight: 400;
  color: var(--muted);
  letter-spacing: 0;
}
.count {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.2rem 0.8rem;
  margin: 0 0 0.7rem;
}
.days {
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.01em;
}
/* Monospace marks hard dates only. */
.mono {
  font-family: var(--font-mono);
}
.count .mono {
  font-size: var(--fs-sm);
  color: var(--muted);
}
.bar {
  height: 0.35rem;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--ink) 14%, var(--paper));
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}
.tally {
  margin: 0.4rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}

.group-title {
  margin: 1.5rem 0 0.5rem;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  border: 0;
}
.empty {
  margin: 0 0 0.5rem;
  font-size: var(--fs-sm);
  color: var(--muted);
}

.due {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
}
.due-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  color: inherit;
  text-decoration: none;
}
.due-head:hover .due-label {
  color: var(--accent);
}
.check {
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: var(--paper);
}
.due-label {
  font-size: var(--fs-md);
  font-weight: 600;
}
.due-cta {
  display: inline-block;
  margin-top: 0.9rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius);
  background: var(--accent);
  color: var(--accent-ink);
  font-size: var(--fs-sm);
  font-weight: 600;
  text-decoration: none;
}

.group {
  margin-top: 0.5rem;
}
.row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
}
.group .row:first-of-type {
  border-top: 1px solid var(--line);
}
.row:hover .what {
  color: var(--accent);
}
.when {
  flex-shrink: 0;
  font-size: var(--fs-sm);
  color: var(--muted);
  white-space: nowrap;
}

.plan-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 1.5rem 0 0;
}
.btn {
  padding: 0.5rem 1rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  font-size: var(--fs-sm);
  text-decoration: none;
  color: var(--ink);
}
.btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.link {
  border: 0;
  background: none;
  padding: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  text-decoration: underline;
  cursor: pointer;
}
.link:hover {
  color: var(--accent);
}

.split {
  display: grid;
  gap: 1.5rem;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
  align-content: start;
  gap: 0.75rem;
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-left: 3px solid var(--line);
  border-radius: var(--radius);
  padding: 0.7rem 0.9rem;
}
.card.active {
  border-left-color: var(--accent);
}
.card-pick {
  border: 0;
  background: none;
  padding: 0;
  font-size: var(--fs-md);
  font-weight: 600;
  color: inherit;
  cursor: pointer;
}
.card-pick:hover {
  color: var(--accent);
}
.card .date {
  margin: 0.1rem 0 0.5rem;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.links {
  display: flex;
  gap: 0.9rem;
  margin: 0;
  font-size: var(--fs-sm);
}
.links button {
  border: 0;
  background: none;
  padding: 0;
  color: var(--muted);
  font-size: inherit;
  text-decoration: underline;
  cursor: pointer;
}
.links button:hover {
  color: var(--warn);
}

@media (min-width: 60rem) {
  .split {
    grid-template-columns: minmax(0, 1fr) 15rem;
    align-items: start;
    gap: 2.5rem;
  }
  .cards {
    grid-template-columns: 1fr;
  }
}
</style>
