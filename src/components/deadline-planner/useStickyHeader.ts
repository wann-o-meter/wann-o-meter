import { computed, onBeforeUnmount, onMounted, ref, type Ref } from "vue";

export function useStickyHeader(
  rootEl: Ref<HTMLElement | null>,
  headerEl: Ref<HTMLElement | null>,
  sentinelEl: Ref<HTMLElement | null>,
) {
  const stuck = ref(false);
  const headerH = ref(0);
  const looseHeaderH = ref(0);

  const headerGap = computed(() =>
    Math.max(0, looseHeaderH.value - headerH.value),
  );

  const observers: (IntersectionObserver | ResizeObserver)[] = [];

  onMounted(() => {
    document.documentElement.style.overflowAnchor = "none";

    if (sentinelEl.value) {
      const io = new IntersectionObserver(
        ([entry]) => {
          if (!entry.isIntersecting) looseHeaderH.value = headerH.value;
          stuck.value = !entry.isIntersecting;
        },
        { threshold: 0 },
      );
      io.observe(sentinelEl.value);
      observers.push(io);
    }

    if (headerEl.value && rootEl.value) {
      const ro = new ResizeObserver(() => {
        const h = headerEl.value?.offsetHeight ?? 0;
        headerH.value = h;
        if (!stuck.value && h >= looseHeaderH.value) looseHeaderH.value = h;
        rootEl.value?.style.setProperty("--tl-header-h", `${h}px`);
      });
      ro.observe(headerEl.value);
      observers.push(ro);
    }
  });

  onBeforeUnmount(() => {
    document.documentElement.style.removeProperty("overflow-anchor");
    observers.forEach((o) => o.disconnect());
  });

  return { stuck, headerGap };
}
