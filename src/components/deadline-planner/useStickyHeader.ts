import { computed, onBeforeUnmount, onMounted, ref, type Ref } from "vue";

/**
 * A sentinel above the header decides when it is stuck, and the timeline then
 * shrinks instead of being clipped. The measured height is published as
 * --tl-header-h on the root, so a card scrolled into view stops below the
 * header, never behind it.
 *
 * Scroll anchoring has to go while this is on screen: the header changing
 * height above the reader's position makes the browser correct the scroll
 * back, which unsticks the header, which grows it again, and the page then
 * refuses to move until you push past the whole loop.
 */
export function useStickyHeader(
  rootEl: Ref<HTMLElement | null>,
  headerEl: Ref<HTMLElement | null>,
  sentinelEl: Ref<HTMLElement | null>,
) {
  const stuck = ref(false);
  const headerH = ref(0);
  const looseHeaderH = ref(0); // its height before it ever shrank

  // Shrinking costs the list its place, so the header hands the freed height
  // back as margin, frame by frame while the strip morphs: the compact bar
  // pins at the top and nothing below it moves at all.
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
