<template>
  <article class="plan">
    <div class="body">
      <p class="meta">
        {{ v.label }}<template v-if="place"> · {{ place }}</template> ·
        <span>{{ shortDate(plan.date) }}</span>
      </p>

      <h2 v-if="!next">Alle Fristen erledigt</h2>
      <h2 v-else-if="span!.days < 0" class="late">
        <AlertTriangle :size="20" aria-hidden="true" />
        <span
          ><span>{{ span!.n }}</span> {{ span!.unit }} überfällig</span
        >
      </h2>
      <h2 v-else-if="span!.days === 0">Heute fällig</h2>
      <h2 v-else>
        Fällig in <span>{{ span!.n }}</span> {{ span!.unit }}
      </h2>

      <p v-if="next" class="next">
        Als Nächstes: <b>{{ next.label }}</b> bis
        <span>{{ shortDate(next.date!) }}</span>
      </p>

      <p v-if="doneCount > 0" class="tally">
        <span>{{ doneCount }}</span> von <span>{{ total }}</span> Fristen
        erledigt.
      </p>

      <div class="row">
        <a class="cta" :href="href">
          Plan öffnen <ArrowRight :size="14" />
        </a>
      </div>
    </div>

    <!-- Only worth a grid while the next Frist is in the month you are in. -->
    <div v-if="calendar" class="cal" aria-hidden="true">
      <p class="cal-head">{{ calendar.month }}</p>
      <div class="grid">
        <span v-for="wd in WEEKDAY_NAMES_SHORT" :key="wd" class="wd">{{
          wd
        }}</span>
        <span
          v-for="(day, i) in calendar.days"
          :key="i"
          :class="dayClass(day)"
          >{{ day ? Number(day.slice(-2)) : "" }}</span
        >
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, ArrowRight } from "lucide-vue-next";
import { computeSchedule } from "../../lib/deadline-plan";
import { appliesTo } from "../../lib/facets";
import {
  WEEKDAY_NAMES_SHORT,
  daysUntil,
  monthLabel,
  shortDate,
  spanParts,
} from "../../lib/date-display";
import {
  planStorageKey,
  readSnapshot,
  snapshotDeadlines,
} from "../../lib/saved-plans";
import { STATES } from "../../lib/states";
import { isoToday } from "../../lib/today";
import type { SavedPlan } from "../../lib/saved-plans";
import type { VorhabenData } from "../../lib/vorhaben-data";

const props = defineProps<{
  plan: SavedPlan;
  v: VorhabenData;
}>();

defineEmits<{ (e: "forget", slug: string): void }>();

const TODAY = isoToday();

const variant = computed(
  () =>
    props.v.variants.find((x) => x.slug === props.plan.variant) ??
    props.v.variants[0],
);
const local = computed(() => variant.value.slug !== "bundesweit");
// Without a local variant the Ort is only known if the visitor picked one,
// otherwise the Bundesland is all the plan says about the place.
const place = computed(() =>
  local.value
    ? variant.value.label
    : (props.plan.ort ?? STATES[props.plan.region ?? ""] ?? ""),
);

const snap = computed(() =>
  readSnapshot(planStorageKey(props.v.vorhaben, variant.value.slug)),
);
// Same facets and edits the plan page applies, otherwise the counts disagree.
const entries = computed(() =>
  computeSchedule(
    props.plan.date,
    snapshotDeadlines(
      variant.value.deadlines.filter((d) => appliesTo(d, props.plan.facets)),
      snap.value,
    ),
    "DE",
    variant.value.regionCode ?? props.plan.region,
  ).filter((e) => e.date !== null),
);

const total = computed(() => entries.value.length);
const doneCount = computed(
  () => entries.value.filter((e) => snap.value.done[e.id]).length,
);
const next = computed(
  () => entries.value.find((e) => !snap.value.done[e.id]) ?? null,
);

// The countdown belongs to the next Frist: the Termin itself never goes wrong.
const span = computed(() => {
  if (!next.value?.date) return null;
  const days = daysUntil(next.value.date, TODAY);
  return { days, ...spanParts(days) };
});

// Leading blanks so the first day sits under its weekday, Monday first.
const calendar = computed(() => {
  const due = next.value?.date;
  if (!due || due.slice(0, 7) !== TODAY.slice(0, 7)) return null;
  const [year, month] = TODAY.split("-").map(Number);
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const firstWeekday =
    (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7;
  const days: (string | null)[] = Array(firstWeekday).fill(null);
  for (let d = 1; d <= lastDay; d++)
    days.push(`${TODAY.slice(0, 7)}-${String(d).padStart(2, "0")}`);
  return { days, month: monthLabel(TODAY, year) };
});

function dayClass(day: string | null): string {
  if (!day) return "";
  if (day === next.value?.date)
    return span.value!.days < 0 ? "due late" : "due";
  return day === TODAY ? "today" : "";
}

// An Ort with its own file brings its Bundesland along, region is only for the
// bundesweit plan of a place we have no file for.
const href = computed(() =>
  local.value
    ? `/${props.v.slug}/${variant.value.slug}/#date=${props.plan.date}`
    : `/${props.v.slug}/#date=${props.plan.date}` +
      (props.plan.region ? `&region=${props.plan.region}` : "") +
      (props.plan.ort ? `&ort=${encodeURIComponent(props.plan.ort)}` : ""),
);
</script>

<style scoped>
.plan {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.6rem 1.2rem;
  height: 100%;
  /* The visitor's own plan is the one card worth lifting off the page. */
  background: var(--grad-card);
  border: 1px solid var(--line);
  border-left: 3px solid var(--anchor);
  border-radius: var(--radius);
  padding: 0.9rem 1.1rem;
}
.body {
  display: flex;
  flex-direction: column;
  flex: 1 1 13rem;
  min-width: 0;
  /* Frist labels are long compound nouns, they have to be allowed to break. */
  overflow-wrap: anywhere;
}
.meta {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
h2 {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin: 0 0 0.3rem;
  border: 0;
  padding: 0;
  font-size: var(--fs-lg);
}
h2.late {
  color: var(--warn);
}

.next {
  margin: 0;
  font-size: var(--fs-sm);
}
.tally {
  margin: 0.2rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 1rem;
  margin-top: auto;
}
.cta {
  margin-top: 0.7rem;
  padding: 0.35rem 0.8rem;
  font-size: var(--fs-sm);
}
/* Removing a plan sits next to the way in, but reads as an aside. */
.forget {
  margin-top: 0.7rem;
  padding: 0;
  border: 0;
  background: none;
  color: var(--muted);
  font-size: var(--fs-sm);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
.forget:hover {
  color: var(--warn);
}

.cal {
  align-self: flex-start;
  width: max-content;
  font-size: var(--fs-xs);
}
.cal-head {
  margin: 0 0 0.15rem;
  color: var(--muted);
  font-weight: 600;
}
.grid {
  display: grid;
  grid-template-columns: repeat(7, 1.3rem);
  gap: 0.05rem;
}
.grid span {
  line-height: 1.3rem;
  text-align: center;
  border-radius: var(--radius-sm);
}
.wd {
  color: var(--muted);
}
/* Today is a ring, the Frist is filled: the two never read as the same mark. */
.today {
  box-shadow: inset 0 0 0 1px var(--muted);
  font-weight: 600;
}
.due {
  background: var(--accent);
  color: var(--accent-ink);
  font-weight: 600;
}
.due.late {
  background: var(--warn);
  color: var(--warn-ink);
}
</style>
