<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef } from "vue";
import { Check, MapPin, Search } from "lucide-vue-next";
import { loadGemeinden, searchGemeinden } from "../../../lib/gemeinde-search";
import type { Gemeinde } from "../../../lib/gemeinde-search";
import type { PlanVariant } from "./types";

const props = defineProps<{
  label: string;
  variantLabel: string;
  variants: PlanVariant[];
  bundesweitSlug: string;
}>();

const emit = defineEmits<{ (e: "pick", g: Gemeinde | null): void }>();

const COUNT = 10;
// The four biggest, so the open list is not just the handful of Orte we happen
// to have Fristen for.
const BIG_CITIES = ["Berlin", "Hamburg", "München", "Frankfurt am Main"];

const open = ref(false);
const query = ref("");
const active = ref(0);
const gemeinden = ref<Gemeinde[]>([]);
const inputEl = useTemplateRef<HTMLInputElement>("inputEl");

const covered = computed<Gemeinde[]>(() =>
  props.variants
    .filter((v) => v.slug !== props.bundesweitSlug)
    .map((v) => ({
      name: v.label,
      plz: gemeinden.value.find((g) => g.name === v.label)?.plz ?? "",
      state: v.regionCode ?? "",
    })),
);

const results = computed<Gemeinde[]>(() => {
  if (query.value.trim().length === 0)
    return [
      ...covered.value,
      ...BIG_CITIES.map((n) => gemeinden.value.find((g) => g.name === n)).filter(
        (g): g is Gemeinde => !!g && !isCovered(g),
      ),
    ].slice(0, COUNT);
  return searchGemeinden(gemeinden.value, query.value, COUNT);
});

const isCovered = (g: Gemeinde) =>
  props.variants.some((v) => v.label === g.name);

async function openPicker() {
  open.value = true;
  query.value = "";
  active.value = 0;
  await nextTick();
  inputEl.value?.focus();
  gemeinden.value = await loadGemeinden();
}

function close() {
  open.value = false;
}

function choose(g: Gemeinde | null) {
  emit("pick", g);
  close();
}

// A typo with no hits should not silently reset the plan to ganz Deutschland.
function confirm() {
  if (active.value < 0 && query.value.trim().length > 0) return;
  choose(results.value[active.value] ?? null);
}

// Index -1 is the "Ganz Deutschland" row above the results, so the cycle runs
// from -1 and the keyboard reaches it too.
function move(step: number) {
  const n = results.value.length + 1;
  active.value = ((active.value + 1 + step + n) % n) - 1;
}
</script>

<template>
  <span class="ort">
    <button
      type="button"
      class="slot"
      :aria-label="variantLabel"
      :aria-expanded="open"
      @click="openPicker"
    >
      <MapPin :size="16" class="pin" aria-hidden="true" />{{ label }}
    </button>

    <div v-if="open" class="pop t-meta">
      <div class="search">
        <Search :size="15" aria-hidden="true" />
        <input
          ref="inputEl"
          v-model="query"
          type="text"
          placeholder="Gemeinde oder PLZ"
          role="combobox"
          aria-controls="ort-list"
          :aria-expanded="results.length > 0"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter.prevent="confirm"
          @keydown.esc="close"
          @blur="close"
        />
      </div>
      <ul id="ort-list" role="listbox">
        <li
          role="option"
          :aria-selected="false"
          :class="{ on: active === -1 }"
          @mousedown.prevent="choose(null)"
        >
          <span>Ganz Deutschland</span>
        </li>
        <li
          v-for="(g, i) in results"
          :key="`${g.name}-${g.plz}`"
          role="option"
          :aria-selected="i === active"
          :class="{ on: i === active }"
          @mousedown.prevent="choose(g)"
        >
          <span class="name">
            <MapPin :size="13" class="pin" aria-hidden="true" />
            <span v-if="g.plz" class="plz">{{ g.plz }}</span>
            <span class="label">{{ g.name }}</span>
          </span>
          <span v-if="isCovered(g)" class="tag covered">
            <Check :size="12" aria-hidden="true" /> örtliche Fristen
          </span>
        </li>
      </ul>
    </div>
  </span>
</template>

<style scoped>
/* Deliberately not positioned: the popover anchors to the nearest positioned
ancestor instead, so it opens at the left of the whole heading and cannot hang
off the right edge when the Ort sits at the end of a long line. */
.ort {
  display: inline-block;
}
.slot {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  color: var(--accent);
  font: inherit;
  cursor: pointer;
}
.slot:hover {
  text-decoration: underline;
  text-underline-offset: 0.15em;
}

.pop {
  position: absolute;
  top: calc(100% + 0.4rem);
  left: 0;
  z-index: 60;
  width: min(22rem, 100%);
  padding: 0.4rem;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--paper-raised);
  box-shadow: var(--shadow-md);
}
.search {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding-left: 0.5rem;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  color: var(--muted);
}
.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  font-size: var(--t-meta);
}
.search:focus-within {
  border-color: var(--accent);
}

ul {
  max-height: 17rem;
  overflow-y: auto;
  margin: 0.3rem 0 0;
  padding: 0;
  list-style: none;
}
li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.4rem 0.5rem;
  border-radius: var(--r-sm);
  font-size: var(--t-meta);
  cursor: pointer;
}
li.on,
li:hover {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
/* The name owns the leftover width and clips, the tag never gets pushed onto a
second line. */
.name {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  min-width: 0;
}
.label {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pin {
  flex-shrink: 0;
  align-self: center;
  color: var(--muted);
}
.slot .pin {
  margin-right: 0.15em;
  vertical-align: -0.1em;
  color: inherit;
}
.plz {
  flex-shrink: 0;
  font-size: var(--t-meta);
  color: var(--muted);
}
.tag {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  flex-shrink: 0;
  font-size: var(--t-meta);
  color: var(--done);
}

@media print {
  .slot {
    border-bottom: 0;
    color: inherit;
  }
  .slot .pin {
    display: none;
  }
  .pop {
    display: none;
  }
}
</style>
