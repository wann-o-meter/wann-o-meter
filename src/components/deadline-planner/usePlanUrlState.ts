import { computed, ref, watch } from "vue";
import { FACET_LABELS, appliesTo, facetsUsedBy } from "../../../lib/facets";
import { STATES } from "../../../lib/states";
import { isoToday } from "../../../lib/today";
import { PLAN_SEGMENT, readPlanState, writePlanState } from "../../../lib/plan-url";
import type { PlanVariant } from "./types";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
// Kept in sync by hand with lib/vorhaben-data, importing it would pull node:fs
// into the browser bundle.
const BUNDESWEIT_SLUG = "bundesweit";

function defaultAnchorDate(deadlines: PlanVariant["deadlines"]): string {
  const offsets = deadlines
    .map((d) => d.offset_days)
    .filter((o): o is number => o !== null);
  if (offsets.length === 0) return isoToday();
  const d = new Date(`${isoToday()}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - Math.min(...offsets));
  return d.toISOString().slice(0, 10);
}

export function usePlanUrlState(
  vorhabenSlug: string,
  variants: PlanVariant[],
  defaultSlug: string | undefined,
) {
  const params = typeof window === "undefined" ? null : readPlanState();
  const has = (slug: string | null | undefined) =>
    !!slug && variants.some((v) => v.slug === slug);

  const urlVariant = params?.get("variant");
  const selectedSlug = ref(
    has(urlVariant)
      ? urlVariant!
      : has(defaultSlug)
        ? defaultSlug!
        : variants[0]?.slug,
  );
  // Bundesweit has no Bundesland of its own, so the startpage passes the one of
  // the picked Ort along, otherwise its Feiertage silently drop out here.
  const region = ref(params?.get("region") ?? "");
  const urlRegion = computed(() =>
    region.value in STATES ? region.value : undefined,
  );
  // The Ort the visitor picked without us having a file for it: it names no
  // extra Fristen, only the Bundesland, but the title should still say it.
  const ortName = ref(params?.get("ort") ?? "");
  const selected = computed(() => {
    const v = variants.find((x) => x.slug === selectedSlug.value) ?? variants[0];
    return v && !v.regionCode && urlRegion.value
      ? { ...v, regionCode: urlRegion.value }
      : v;
  });

  const urlDate = params?.get("date");
  const anchorDate = ref(
    urlDate && ISO_DAY.test(urlDate)
      ? urlDate
      : defaultAnchorDate(
        variants.find((v) => v.slug === selectedSlug.value)?.deadlines ?? [],
      ),
  );

  const activeFacets = ref<string[]>(
    (params?.get("facets") ?? "").split(",").filter((f) => f in FACET_LABELS),
  );
  const facetOptions = computed(() =>
    facetsUsedBy(selected.value?.deadlines ?? []),
  );

  // A date in the URL means the visitor picked one, an auto default does not.
  const touched = ref(params?.has("date") ?? false);
  watch(
    [anchorDate, selectedSlug, activeFacets, ortName],
    () => (touched.value = true),
  );

  const overlapMonths = ref(params?.get("overlap") === "1" ? 1 : 0);
  const deferred = computed(() => overlapMonths.value > 0);
  const toggleDefer = () => (overlapMonths.value = deferred.value ? 0 : 1);

  const selectedForPlan = computed(() =>
    selected.value
      ? {
        ...selected.value,
        deadlines: selected.value.deadlines.filter((d) =>
          appliesTo(d, activeFacets.value),
        ),
      }
      : undefined,
  );

  // One address for the plan of a Vorhaben. The Ort is part of the state, not
  // part of the path: changing it must not walk the visitor onto another page.
  const planPath = `/${vorhabenSlug}/${PLAN_SEGMENT}/`;

  // The wizard marks the arrival that follows "Plan öffnen". One letter, because
  // it is a note to the page and not to the visitor, and it is spent on arrival:
  // a reload, a bookmark or a shared link opens the plan without the entrance,
  // which is what makes it an entrance.
  const fresh = ref(params?.get("n") === "1");
  if (fresh.value) writePlanState(planPath, { n: null });

  // The other state only reaches the URL once the visitor picked something, an
  // untouched page keeps its clean URL and stays out of the saved plans.
  watch(
    [touched, anchorDate, selectedSlug, activeFacets, overlapMonths, region, ortName],
    () => {
      // region and ort only carry an Ort we have no file for. A variant that
      // knows its own Bundesland makes both redundant.
      const hasOwnRegion = !!variants.find(
        (x) => x.slug === selectedSlug.value,
      )?.regionCode;
      writePlanState(planPath, {
        variant:
          selectedSlug.value === BUNDESWEIT_SLUG ? null : selectedSlug.value,
        region: hasOwnRegion ? null : region.value || null,
        ort: hasOwnRegion ? null : ortName.value || null,
        date: touched.value && anchorDate.value ? anchorDate.value : null,
        facets:
          touched.value && activeFacets.value.length > 0
            ? activeFacets.value.join(",")
            : null,
        overlap: touched.value && deferred.value ? "1" : null,
      });
    },
    { immediate: true },
  );

  return {
    selectedSlug,
    selected,
    region,
    ortName,
    selectedForPlan,
    anchorDate,
    activeFacets,
    facetOptions,
    overlapMonths,
    deferred,
    toggleDefer,
    touched,
    fresh,
  };
}
