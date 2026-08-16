<script setup lang="ts">
import { computed, ref } from "vue";
import { Search } from "lucide-vue-next";
import { fold } from "../../lib/gemeinde-search";

export interface FristEntry {
  id: string;
  label: string;
  source: string;
  tags: string[];
  note?: string;
  plans: { slug: string; label: string }[];
}

const props = defineProps<{ fristen: FristEntry[] }>();

const query = ref("");
const filter = ref("");

const title = (s: string) => s[0].toUpperCase() + s.slice(1);
// A Frist is filed under its plan, or under the first of its own tags when no
// plan claims it yet. The rest of the tags are words to search for, not groups.
const groupsOf = (f: FristEntry) =>
  f.plans.length > 0
    ? f.plans.map((p) => ({ id: p.slug, label: p.label }))
    : f.tags.slice(0, 1).map((t) => ({ id: t, label: title(t) }));

// Someone types muenchen or münchen or munchen and means the same place, so
// both spellings of every umlaut have to match.
const forms = (s: string) => [
  fold(s),
  fold(s.replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue")),
];
const hit = (field: string, query: string) =>
  forms(query).some((q) => forms(field).some((f) => f.includes(q)));

const filters = computed(() => {
  const seen = new Map<string, string>();
  for (const f of props.fristen)
    for (const g of groupsOf(f)) seen.set(g.id, g.label);
  return [...seen].map(([id, label]) => ({ id, label }));
});

const matches = computed(() => {
  const q = query.value.trim();
  return props.fristen.filter((f) => {
    if (filter.value && !groupsOf(f).some((g) => g.id === filter.value))
      return false;
    if (!q) return true;
    // Not the note: it is prose, and prose matches things nobody searched for.
    return [f.label, f.source, ...f.tags, ...f.plans.map((p) => p.label)].some(
      (field) => hit(field, q),
    );
  });
});

const toggle = (id: string) => (filter.value = filter.value === id ? "" : id);
</script>

<template>
  <section id="fristen" class="finder">
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
          <span class="tags">
            <span v-for="g in groupsOf(f)" :key="g.id" class="tag">{{
              g.label
            }}</span>
          </span>
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
  margin-top: var(--section-gap);
}
/* Same shape as the picker above: heading, one line, then the controls. */
h2 {
  font-size: var(--fs-lg);
  border: 0;
  padding: 0;
  margin: 0 0 0.25rem;
}
.lede {
  max-width: 62ch;
  margin: 0 0 1.25rem;
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
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.3rem 1rem;
  padding: 0.6rem 0.9rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper-raised);
  transition:
    border-color 0.12s,
    box-shadow 0.12s;
}
li:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-card);
}
li a {
  font-weight: 600;
  text-decoration: none;
}
li:hover a {
  color: var(--accent);
}
/* The title carries the link, the whole card is its hit area. */
li a::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
/* Two fixed tracks, so the paragraph and the tag line up down the list instead
of drifting with the length of each. */
.meta {
  display: grid;
  grid-template-columns: 1fr 7rem;
  align-items: baseline;
  gap: 0.5rem;
  width: 19rem;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.src {
  text-align: right;
}
@media (max-width: 34rem) {
  .meta {
    width: auto;
    grid-template-columns: auto auto;
    justify-content: start;
  }
  .src {
    text-align: left;
  }
}
.tags {
  display: flex;
  gap: 0.3rem;
}
.tag {
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  padding: 0.05rem 0.5rem;
  white-space: nowrap;
}
.tag {
  border-color: color-mix(in srgb, var(--accent) 40%, var(--line));
  color: var(--accent);
}
.empty {
  color: var(--muted);
  font-size: var(--fs-sm);
}
</style>
