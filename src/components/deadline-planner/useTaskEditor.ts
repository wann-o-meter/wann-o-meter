import { type ComputedRef, computed, reactive, ref, watch } from "vue";
import type { Deadline, ScheduleEntry } from "../../../lib/deadline-plan";
import type { PlanVariant } from "./types";
import { LETTER_TEMPLATE } from "./task-cta";
import { readPlanState, writePlanState } from "../../../lib/plan-url";

const CUSTOM_PREFIX = "custom-";

function isCustomTask(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

interface CustomTask {
  id: string;
  label: string;
  offsetDays: number;
}

function urlHiddenIds(): string[] {
  return (readPlanState().get("hidden") ?? "").split(",").filter(Boolean);
}

export function useTaskEditor(
  selected: ComputedRef<PlanVariant | undefined>,
  storageKey?: ComputedRef<string>,
) {
  let customUid = 0;
  const customTasks = ref<CustomTask[]>([]);
  const doneIds = reactive<Record<string, boolean>>({});
  const hiddenIds = reactive<Record<string, boolean>>({});
  const userNotes = reactive<Record<string, string>>({});
  const labelOverrides = reactive<Record<string, string>>({});
  const attachments = reactive<Record<string, string>>({});
  const lastHidden = ref<{ id: string; label: string } | null>(null);

  const workingDeadlines = computed<Deadline[]>(() => {
    if (!selected.value) return [];
    const custom: Deadline[] = customTasks.value.map((t) => ({
      id: t.id,
      kind: "soft" as const,
      belongsTo: [],
      tags: [],
      label: t.label,
      offset_days: t.offsetDays,
      source_url: null,
    }));
    return [...selected.value.deadlines, ...custom]
      .filter((d) => !hiddenIds[d.id])
      .map((d) =>
        d.id in labelOverrides ? { ...d, label: labelOverrides[d.id] } : d,
      );
  });

  function toggleDone(id: string) {
    doneIds[id] = !doneIds[id];
  }

  function commitLabel(id: string, value: string) {
    const label = value.trim();
    const task = customTasks.value.find((t) => t.id === id);
    if (task) task.label = label || "Ohne Titel";
    else if (label) labelOverrides[id] = label;
    else delete labelOverrides[id];
  }

  function commitNote(id: string, value: string) {
    const trimmed = value.trim();
    if (trimmed) userNotes[id] = trimmed;
    else delete userNotes[id];
  }

  function commitAttachment(id: string, value: string) {
    const trimmed = value.trim();
    if (trimmed) attachments[id] = trimmed;
    else delete attachments[id];
  }

  function ensureAttachment(id: string) {
    if (!(id in attachments)) attachments[id] = LETTER_TEMPLATE;
  }

  function hideEntry(entry: ScheduleEntry) {
    hiddenIds[entry.id] = true;
    lastHidden.value = { id: entry.id, label: entry.label };
  }

  function unhide(id?: string) {
    const target = id ?? lastHidden.value?.id;
    if (!target) return;
    delete hiddenIds[target];
    if (lastHidden.value?.id === target) lastHidden.value = null;
  }

  const hiddenTasks = computed(() =>
    [
      ...(selected.value?.deadlines ?? []),
      ...customTasks.value.map((t) => ({ id: t.id, label: t.label })),
    ]
      .filter((d) => hiddenIds[d.id])
      .map((d) => ({ id: d.id, label: labelOverrides[d.id] ?? d.label })),
  );

  function addTaskAtEnd(knownOffsets: number[], label = "") {
    const offset =
      (knownOffsets.length > 0 ? Math.max(...knownOffsets) : 0) + 3;
    const id = `${CUSTOM_PREFIX}${++customUid}`;
    customTasks.value.push({ id, label, offsetDays: offset });
    return id;
  }

  const maps = {
    done: doneIds,
    hidden: hiddenIds,
    notes: userNotes,
    labels: labelOverrides,
    attachments,
  } as const;

  function restore(raw: string | null) {
    for (const map of Object.values(maps))
      for (const key of Object.keys(map)) delete map[key];
    customTasks.value = [];
    customUid = 0;
    if (!raw) return;
    let saved;
    try {
      saved = JSON.parse(raw);
    } catch {
      return;
    }
    for (const [name, map] of Object.entries(maps))
      Object.assign(map, saved[name] ?? {});
    // Plans saved before hiding got its own name.
    Object.assign(hiddenIds, saved.deleted ?? {});
    customTasks.value = Array.isArray(saved.custom) ? saved.custom : [];
    for (const task of customTasks.value)
      customUid = Math.max(
        customUid,
        Number(task.id.slice(CUSTOM_PREFIX.length)) || 0,
      );
  }

  if (storageKey && typeof localStorage !== "undefined") {
    watch(storageKey, (key) => restore(localStorage.getItem(key)), {
      immediate: true,
    });
    watch(
      [doneIds, hiddenIds, userNotes, labelOverrides, attachments, customTasks],
      () => {
        const snapshot = Object.fromEntries(
          Object.entries(maps).map(([name, map]) => [name, { ...map }]),
        );
        try {
          localStorage.setItem(
            storageKey.value,
            JSON.stringify({ ...snapshot, custom: customTasks.value }),
          );
        } catch {
        }
      },
      { deep: true },
    );
  }

  // What the visitor put aside travels with the link, the rest of the plan
  // already does.
  for (const id of urlHiddenIds()) hiddenIds[id] = true;
  watch(
    hiddenIds,
    () => {
      if (typeof window === "undefined") return;
      const ids = Object.keys(hiddenIds).filter((id) => hiddenIds[id]);
      writePlanState(window.location.pathname, {
        hidden: ids.length > 0 ? ids.join(",") : null,
      });
    },
    { deep: true },
  );

  return {
    doneIds,
    userNotes,
    attachments,
    lastHidden,
    hiddenTasks,
    workingDeadlines,
    isCustom: isCustomTask,
    toggleDone,
    commitLabel,
    commitNote,
    commitAttachment,
    ensureAttachment,
    hideEntry,
    unhide,
    addTaskAtEnd,
  };
}
