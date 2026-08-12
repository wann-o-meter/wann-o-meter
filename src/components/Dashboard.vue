<script setup lang="ts">
import { computed } from "vue";
import { computeSchedule } from "../../lib/deadline-plan";
import type { ScheduleEntry } from "../../lib/deadline-plan";
import { shortDate, longDate } from "../../lib/date-display";
import { formatDate } from "../../lib/format-date";
import { isoToday } from "../../lib/today";
import { dayNum, isoOfDay } from "../../lib/timeline-geometry";
import {
  planStorageKey,
  readSnapshot,
  snapshotDeadlines,
} from "../../lib/saved-plans";
import type { SavedPlan } from "../../lib/saved-plans";
import type { VorhabenData } from "../../lib/vorhaben-data";

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

interface Item {
  id: string;
  view: PlanView;
  entry: ScheduleEntry;
  day: number;
  done: boolean;
}

const TODAY = dayNum(isoToday());

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

const items = computed<Item[]>(() =>
  views.value
    .flatMap((view) =>
      view.entries.map((entry) => ({
        id: `${view.plan.slug}-${entry.id}`,
        view,
        entry,
        day: dayNum(entry.date!),
        done: !!view.done[entry.id],
      })),
    )
    .sort((a, b) => a.day - b.day),
);

const open = computed(() => items.value.filter((i) => !i.done));
const overdue = computed(() => open.value.filter((i) => i.day < TODAY));

const week = (day: number) => Math.floor((day + 3) / 7);

// An overview, not the plan itself: what is late and what comes next.
const SOON = 5;
const upcoming = computed(() => open.value.filter((i) => i.day >= TODAY));
const soon = computed(() => upcoming.value.slice(0, SOON));
const laterCount = computed(() => upcoming.value.length - soon.value.length);

const groups = computed(() =>
  [
    { title: "Überfällig", items: overdue.value },
    { title: "Demnächst", items: soon.value },
  ].filter((g) => g.items.length > 0),
);

// Weeks where two Vorhaben want something at once, the reason this page exists.
const collisions = computed(() => {
  const byWeek = new Map<number, Item[]>();
  for (const item of open.value) {
    if (item.day < TODAY) continue;
    byWeek.set(week(item.day), [...(byWeek.get(week(item.day)) ?? []), item]);
  }
  return [...byWeek.values()]
    .filter((list) => new Set(list.map((i) => i.view.plan.slug)).size > 1)
    .map((list) => ({
      from: week(list[0].day) * 7 - 3,
      labels: [...new Set(list.map((i) => i.view.v.label))].join(" und "),
      titles: list.map((i) => i.entry.label).join(", "),
    }));
});

function relative(item: Item): string {
  const days = item.day - TODAY;
  if (days === 0) return "heute";
  const n = Math.abs(days);
  const unit = n === 1 ? "Tag" : "Tagen";
  return days < 0 ? `vor ${n} ${unit}` : `in ${n} ${unit}`;
}

function nextEntry(view: PlanView): ScheduleEntry | null {
  const rest = view.entries.filter((e) => !view.done[e.id]);
  return rest.find((e) => dayNum(e.date!) >= TODAY) ?? rest[0] ?? null;
}

function progress(view: PlanView): { done: number; total: number } {
  return {
    done: view.entries.filter((e) => view.done[e.id]).length,
    total: view.entries.length,
  };
}
</script>

<template>
  <section class="dashboard">
    <h1>Deine Fristen</h1>
    <p class="lede">
      {{ open.length }} offene {{ open.length === 1 ? "Frist" : "Fristen" }},
      gerechnet ab
      <template v-for="(view, i) in views" :key="view.plan.slug"
        ><template v-if="i > 0">, </template>{{ view.v.label
        }}<span class="mono"> {{ formatDate(view.plan.date) }}</span></template
      >.
      <template v-if="overdue.length">
        <b>{{ overdue.length }}</b> davon
        {{ overdue.length === 1 ? "ist" : "sind" }} überfällig.
      </template>
    </p>

    <div v-for="(c, i) in collisions.slice(0, 2)" :key="i" class="collide">
      In der Woche ab {{ shortDate(isoOfDay(c.from)) }} treffen Fristen aus
      {{ c.labels }} zusammen: {{ c.titles }}.
    </div>

    <div class="split">
      <div class="agenda">
        <div v-for="group in groups" :key="group.title" class="group">
          <h2>{{ group.title }}</h2>
          <a
            v-for="item in group.items"
            :key="item.id"
            class="row"
            :href="item.view.href"
          >
            <span class="rel">{{ relative(item) }}</span>
            <span class="what">{{ item.entry.label }}</span>
            <span v-if="views.length > 1" class="tag">{{
              item.view.v.label
            }}</span>
            <span class="when">{{ shortDate(item.entry.date!) }}</span>
          </a>
        </div>

        <p v-if="laterCount > 0" class="later">
          {{ laterCount }} weitere {{ laterCount === 1 ? "Frist" : "Fristen" }}
          danach, im jeweiligen Zeitplan.
        </p>
      </div>

      <aside class="cards">
      <article v-for="view in views" :key="view.plan.slug" class="card">
        <h3>
          {{ view.v.label }}
          <em
            >{{ progress(view).done }} von {{ progress(view).total }}
            erledigt</em
          >
        </h3>
        <p class="date">
          {{ longDate(view.plan.date)
          }}<template v-if="view.variantLabel">
            · {{ view.variantLabel }}</template
          >
        </p>
        <div class="bar">
          <i
            :style="{
              width: `${Math.round((progress(view).done / Math.max(1, progress(view).total)) * 100)}%`,
            }"
          ></i>
        </div>
        <p class="next">
          <template v-if="nextEntry(view)">
            Nächste Frist: {{ nextEntry(view)!.label }},
            <span class="mono">{{ shortDate(nextEntry(view)!.date!) }}</span>
          </template>
          <template v-else>Alle Fristen erledigt.</template>
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
.lede {
  color: var(--muted);
  margin: 0.25rem 0 0;
}
.lede b {
  color: var(--ink);
}
/* Monospace marks hard dates only. */
.mono {
  font-family: var(--font-mono);
  color: var(--ink);
}

.collide {
  margin-top: 1rem;
  border-left: 3px solid var(--warn);
  background: color-mix(in srgb, var(--warn) 8%, transparent);
  padding: 0.6rem 0.9rem;
  font-size: var(--fs-sm);
}

.group {
  margin-top: 1.5rem;
}
.group h2 {
  font-size: var(--fs-sm);
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
  border: 0;
  margin: 0 0 0.25rem;
}
.row {
  display: grid;
  grid-template-columns: 7rem minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0.1rem 1rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
}
.row:hover .what {
  color: var(--accent);
}
.rel {
  font-weight: 600;
  white-space: nowrap;
}
.when {
  grid-column: 2;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--muted);
  white-space: nowrap;
}
.tag {
  grid-column: 3;
  grid-row: 1;
  font-size: var(--fs-xs);
  color: var(--muted);
  white-space: nowrap;
}

.later {
  margin: 0.75rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}

.split {
  display: grid;
  gap: 1.5rem;
  margin-top: 1.5rem;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  align-content: start;
  gap: 0.75rem;
  order: -1;
}
@media (min-width: 60rem) {
  .split {
    grid-template-columns: minmax(0, 1fr) 17rem;
    align-items: start;
    gap: 2rem;
  }
  .agenda {
    grid-area: 1 / 1;
  }
  .cards {
    grid-area: 1 / 2;
    grid-template-columns: 1fr;
  }
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
}
.card h3 {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0;
  font-size: var(--fs-md);
  border: 0;
}
.card h3 em {
  font-style: normal;
  font-size: var(--fs-xs);
  font-weight: 400;
  color: var(--muted);
}
.card .date {
  margin: 0.1rem 0 0;
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--muted);
}
.bar {
  height: 3px;
  margin: 0.7rem 0 0.5rem;
  background: var(--line);
  border-radius: 2px;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
}
.next {
  margin: 0 0 0.6rem;
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

@media (max-width: 30rem) {
  .row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .rel {
    grid-column: 1;
    grid-row: 2;
  }
  .what {
    grid-column: 1 / -1;
    grid-row: 1;
  }
  .when {
    grid-column: 2;
    grid-row: 2;
  }
  .tag {
    grid-column: 2;
    grid-row: 1;
  }
}
</style>
