import { computed, ref, watch } from "vue";
import { FACET_LABELS, appliesTo, facetsUsedBy } from "../../../lib/facets";
import { isoToday } from "../../../lib/today";
import type { PlanVariant } from "./types";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

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
  const selected = computed(
    () => variants.find((v) => v.slug === selectedSlug.value) ?? variants[0],
  );

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

  watch(
    [anchorDate, selectedSlug, activeFacets, overlapMonths],
    () => {
      if (typeof window === "undefined") return;
      const next = new URLSearchParams(window.location.search);
      if (anchorDate.value) next.set("date", anchorDate.value);
      if (selected.value) next.set("variant", selected.value.slug);
      if (activeFacets.value.length > 0)
        next.set("facets", activeFacets.value.join(","));
      else next.delete("facets");
      if (deferred.value) next.set("overlap", "1");
      else next.delete("overlap");
      const query = next.toString();
      history.replaceState(
        null,
        "",
        query ? `?${query}` : window.location.pathname,
      );
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
  };
}
