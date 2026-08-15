import { computed, ref, watch } from "vue";
import { FACET_LABELS, appliesTo, facetsUsedBy } from "../../../lib/facets";
import { STATES } from "../../../lib/states";
import { isoToday } from "../../../lib/today";
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
  const params =
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search);
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
  const region = params?.get("region");
  const urlRegion = region && region in STATES ? region : undefined;
  const selected = computed(() => {
    const v = variants.find((x) => x.slug === selectedSlug.value) ?? variants[0];
    return v && !v.regionCode && urlRegion ? { ...v, regionCode: urlRegion } : v;
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
  watch([anchorDate, selectedSlug, activeFacets], () => (touched.value = true));

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

  // The Ort belongs in the path, otherwise /umzug/rottenburg/?variant=singen
  // shows two different places at once. The query is still read on arrival so
  // links shared before this stay valid.
  const variantPath = (slug: string) =>
    slug === BUNDESWEIT_SLUG
      ? `/${vorhabenSlug}/`
      : `/${vorhabenSlug}/${slug}/`;

  // The other state only reaches the URL once the visitor picked something, an
  // untouched page keeps its clean URL and stays out of the saved plans.
  watch(
    [touched, anchorDate, selectedSlug, activeFacets, overlapMonths],
    () => {
      if (typeof window === "undefined") return;
      const next = new URLSearchParams(window.location.search);
      next.delete("variant");
      // region only carries the Bundesland of an Ort we have no file for. A
      // variant that knows its own Bundesland makes it redundant.
      if (variants.find((x) => x.slug === selectedSlug.value)?.regionCode)
        next.delete("region");
      if (touched.value) {
        if (anchorDate.value) next.set("date", anchorDate.value);
        if (activeFacets.value.length > 0)
          next.set("facets", activeFacets.value.join(","));
        else next.delete("facets");
        if (deferred.value) next.set("overlap", "1");
        else next.delete("overlap");
      }
      const path = variantPath(selected.value?.slug ?? BUNDESWEIT_SLUG);
      const query = next.toString();
      history.replaceState(null, "", query ? `${path}?${query}` : path);
    },
    { immediate: true },
  );

  return {
    selectedSlug,
    selected,
    selectedForPlan,
    anchorDate,
    activeFacets,
    facetOptions,
    overlapMonths,
    deferred,
    toggleDefer,
    touched,
  };
}
