<script setup lang="ts">
import { computed, ref } from "vue";
import { Search } from "lucide-vue-next";
import { fold } from "../../lib/gemeinde-search";

export interface FristEntry {
  id: string;
  label: string;
  source: string;
  // A statute that names the day itself, rather than counting from your date.
  fixed: boolean;
  note?: string;
  plans: { slug: string; label: string }[];
}

const props = defineProps<{ fristen: FristEntry[] }>();

const FIXED = "__fixed";
const query = ref("");
const filter = ref("");

const filters = computed(() => {
  const plans = new Map<string, string>();
  for (const f of props.fristen)
    for (const p of f.plans) plans.set(p.slug, p.label);
  return [
    ...[...plans].map(([slug, label]) => ({ id: slug, label })),
    ...(props.fristen.some((f) => f.fixed)
      ? [{ id: FIXED, label: "Fester Stichtag" }]
      : []),
  ];
});

const matches = computed(() => {
  const q = fold(query.value.trim());
  return props.fristen.filter((f) => {
    if (filter.value === FIXED && !f.fixed) return false;
    if (filter.value && filter.value !== FIXED)
      if (!f.plans.some((p) => p.slug === filter.value)) return false;
    if (!q) return true;
    return (
      fold(f.label).includes(q) ||
      fold(f.source).includes(q) ||
      fold(f.note ?? "").includes(q)
    );
  });
});

const toggle = (id: string) => (filter.value = filter.value === id ? "" : id);
</script>

<template>
  <section class="finder">
    <h2>Fristen nachschlagen</h2>
    <p class="lede">
      Jede Frist mit dem Paragrafen dahinter. Such nach der Aufgabe oder nach dem
      Gesetz.
    </p>

    <div class="controls">
      <div class="field">
        <Search :size="16" aria-hidden="true" />
        <input
          v-model="query"
          type="search"
          placeholder="Kündigung, Ummeldung, § 573c ..."
          aria-label="Fristen durchsuchen"
        />
      </div>
      <div class="chips" role="group" aria-label="Fristen filtern">
        <button
          v-for="f in filters"
          :key="f.id"
          type="button"
          class="chip key"
          :aria-pressed="filter === f.id"
          @click="toggle(f.id)"
        >
          {{ f.label }}
        </button>
      </div>
    </div>

    <ul v-if="matches.length > 0">
      <li v-for="f in matches" :key="f.id">
        <a :href="`/frist/${f.id}/`">{{ f.label }}</a>
        <span class="meta">
          <span class="src">{{ f.source }}</span>
          <span v-if="f.fixed" class="tag">Fester Stichtag</span>
          <span v-for="p in f.plans" :key="p.slug" class="tag plan">{{
            p.label
          }}</span>
        </span>
      </li>
    </ul>
    <p v-else class="empty">
      Dazu haben wir noch keine Frist. Fehlt eine?
      <a href="/feedback">Sag Bescheid.</a>
    </p>
  </section>
</template>

<style scoped>
.finder {
  margin-top: 4rem;
}
.lede {
  max-width: 62ch;
  color: var(--muted);
  font-size: var(--fs-sm);
}
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem 1rem;
  margin-bottom: 1.25rem;
}
.field {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding-left: 0.6rem;
  width: 100%;
  max-width: 22rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper-raised);
  color: var(--muted);
}
.field:focus-within {
  border-color: var(--accent);
}
.field input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.chip {
  border-radius: var(--radius-pill);
  padding: 0.25rem 0.75rem;
  font-size: var(--fs-sm);
}

ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}
li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.3rem 1rem;
  padding: 0.6rem 0.9rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper-raised);
}
li a {
  font-weight: 600;
}
.meta {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.tag {
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  padding: 0.05rem 0.5rem;
}
.tag.plan {
  border-color: color-mix(in srgb, var(--accent) 40%, var(--line));
  color: var(--accent);
}
.empty {
  color: var(--muted);
  font-size: var(--fs-sm);
}
</style>
