<template>
  <div class="wom-start">
    <h2 v-if="planCards.length > 0" id="plaene" class="t-section mine">
      Deine Pläne
    </h2>
    <TransitionGroup name="plan" tag="div" class="plans">
      <SavedPlanCard
        v-for="card in planCards"
        :key="card.plan.slug"
        :plan="card.plan"
        :v="card.v"
      />
    </TransitionGroup>

    <section class="step">
      <h2 id="q1" class="t-section">Plan erstellen</h2>
      <p class="section-lede t-meta">
        Vorhaben wählen, Termin eingeben und jede Aufgabe mit Datum
        bekommen.
      </p>
      <div class="choices">
        <div v-for="v in vorhaben" :key="v.slug" class="choice">
          <a class="t-title" :href="`/${v.slug}/`">{{ v.label }}</a>
          <small class="t-meta">{{ v.teaser }}</small>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import SavedPlanCard from "./SavedPlanCard.vue";
import { loadSavedPlans } from "../../lib/saved-plans";
import type { SavedPlan } from "../../lib/saved-plans";
import type { VorhabenData } from "../../lib/vorhaben-data";

const props = defineProps<{ vorhaben: VorhabenData[] }>();

const savedPlans = ref<SavedPlan[]>([]);
const planCards = computed(() =>
  savedPlans.value.flatMap((plan) => {
    const v = props.vorhaben.find((x) => x.slug === plan.slug);
    return v ? [{ plan, v }] : [];
  }),
);

// localStorage is not there while the island renders on the server, so the
// cards arrive one tick later and fade in.
onMounted(() => (savedPlans.value = loadSavedPlans()));
</script>

<style scoped>
/* Two plans fit side by side, four stack into two rows, one fills the row. */
h2.mine {
  margin: var(--section-gap) 0 var(--s-1);
}
.plans {
  display: grid;
  /* min() or the 22rem track stays 22rem on a narrower screen and the card
  pushes the page sideways. */
  grid-template-columns: repeat(auto-fit, minmax(min(22rem, 100%), 1fr));
  gap: var(--s-2);
}

/* Saved plans fade in after the storage read and slide out when forgotten. */
.plan-enter-active {
  transition:
    opacity 0.3s ease,
    transform 0.3s cubic-bezier(0.2, 0.8, 0.3, 1);
}
.plan-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.plan-enter-from {
  opacity: 0;
  transform: translateY(0.5rem);
}
.plan-leave-to {
  opacity: 0;
  transform: translateX(-1rem);
}
.plan-move {
  transition: transform 0.3s ease;
}

/* One rhythm: every block of the page starts the same distance below the last. */
.step {
  margin-top: var(--section-gap);
}
h2 {
  margin: 0 0 0.25rem;
}
.section-lede {
  max-width: 62ch;
  margin: 0 0 var(--s-2);
  color: var(--muted);
}

/* Cards, because they lead somewhere. The chip shape belongs to a choice you
make on the page you are on. */
.choices {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--s-1);
}
@media (max-width: 40rem) {
  .choices {
    grid-template-columns: repeat(2, 1fr);
  }
}
.choice {
  position: relative;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: var(--s-2);
}
.choice a {
  color: var(--ink);
  text-decoration: none;
}
/* The whole card is the target, but the link text a crawler reads is the name
of the Vorhaben and nothing else. */
.choice a::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: var(--r-lg);
}
.choice:hover {
  border-color: var(--accent);
}
.choice:hover a {
  color: var(--accent);
}
.choice:focus-within {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.choice small {
  display: block;
  color: var(--muted);
  margin-top: 0.3rem;
  text-wrap: balance;
}
</style>
