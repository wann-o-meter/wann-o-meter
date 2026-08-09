import { type ComputedRef, computed, nextTick, reactive, ref } from "vue";
import type { Deadline, ScheduleEntry } from "../../../lib/deadline-plan";
import type { PlanVariant } from "./types";
import { LETTER_TEMPLATE } from "./task-cta";

const CUSTOM_PREFIX = "custom-";

export function isCustomTask(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

interface CustomTask {
  id: string;
  label: string;
  offsetDays: number;
}

// Client-only editing layer, nothing persisted (no login/storage) - exists so
// the plan can be worked FROM, not just read. `rootEl` is the component root,
// used to focus a task's input right after it's created or opened.
export function useTaskEditor(
  selected: ComputedRef<PlanVariant | undefined>,
  rootEl: { value: HTMLElement | null },
) {
  let customUid = 0;
  const customTasks = ref<CustomTask[]>([]);
  const doneIds = reactive<Record<string, boolean>>({});
  const deletedIds = reactive<Record<string, boolean>>({});
  const userNotes = reactive<Record<string, string>>({});
  // Rescheduling a real (read-only) deadline via moveEntry() - a custom
  // task mutates its own offsetDays instead, see moveEntry() below.
  const offsetOverrides = reactive<Record<string, number>>({});
  const editingId = ref<string | null>(null);
  const openNoteId = ref<string | null>(null);
  // Separate from userNotes on purpose - a note is free-form text, an
  // attachment is the letter CTA's own content (link CTAs are stateless).
  const attachments = reactive<Record<string, string>>({});
  const openAttachmentId = ref<string | null>(null);
  const lastDeleted = ref<{ id: string; label: string } | null>(null);

  function moveEntry(id: string, newOffsetDays: number) {
    const custom = customTasks.value.find((t) => t.id === id);
    if (custom) custom.offsetDays = newOffsetDays;
    else offsetOverrides[id] = newOffsetDays;
  }

  const workingDeadlines = computed<Deadline[]>(() => {
    if (!selected.value) return [];
    const custom: Deadline[] = customTasks.value.map((t) => ({
      id: t.id,
      label: t.label,
      offset_days: t.offsetDays,
      source_url: null,
    }));
    return [...selected.value.deadlines, ...custom]
      .filter((d) => !deletedIds[d.id])
      .map((d) =>
        d.id in offsetOverrides
          ? { ...d, offset_days: offsetOverrides[d.id] }
          : d,
      );
  });

  function focusWithin(selector: string) {
    nextTick(() => {
      const el = rootEl.value?.querySelector<
        HTMLInputElement | HTMLTextAreaElement
      >(selector);
      el?.focus();
      if (el instanceof HTMLInputElement) el.select();
    });
  }

  function toggleDone(id: string) {
    doneIds[id] = !doneIds[id];
  }

  function startEditingLabel(id: string) {
    editingId.value = id;
    focusWithin(`[data-title-input="${id}"]`);
  }

  function commitLabel(id: string, value: string) {
    if (editingId.value !== id) return;
    const task = customTasks.value.find((t) => t.id === id);
    if (task) task.label = value.trim() || "Ohne Titel";
    editingId.value = null;
  }

  function openNote(id: string) {
    openNoteId.value = id;
    focusWithin(`[data-note-input="${id}"]`);
  }

  function commitNote(id: string, value: string) {
    if (openNoteId.value !== id) return;
    const trimmed = value.trim();
    if (trimmed) userNotes[id] = trimmed;
    else delete userNotes[id];
    openNoteId.value = null;
  }

  // Letter CTA only (link CTA is a plain <a>, stateless). First open seeds
  // the template, later opens reuse whatever was written.
  function openAttachment(id: string) {
    if (!(id in attachments)) attachments[id] = LETTER_TEMPLATE;
    openAttachmentId.value = id;
    focusWithin(`[data-attachment-input="${id}"]`);
  }

  function commitAttachment(id: string, value: string) {
    if (openAttachmentId.value !== id) return;
    const trimmed = value.trim();
    if (trimmed) attachments[id] = trimmed;
    else delete attachments[id];
    openAttachmentId.value = null;
  }

  function deleteEntry(entry: ScheduleEntry) {
    deletedIds[entry.id] = true;
    lastDeleted.value = { id: entry.id, label: entry.label };
  }

  function undoDelete() {
    if (!lastDeleted.value) return;
    delete deletedIds[lastDeleted.value.id];
    lastDeleted.value = null;
  }

  function insertCustomTask(
    afterOffset: number,
    beforeOffset: number,
    label = "",
  ) {
    const id = `${CUSTOM_PREFIX}${++customUid}`;
    customTasks.value.push({
      id,
      label,
      offsetDays: Math.round((afterOffset + beforeOffset) / 2),
    });
    if (!label) startEditingLabel(id);
  }

  function addTaskAtEnd(knownOffsets: number[], label = "") {
    const offset = (knownOffsets.length > 0 ? Math.max(...knownOffsets) : 0) + 3;
    const id = `${CUSTOM_PREFIX}${++customUid}`;
    customTasks.value.push({ id, label, offsetDays: offset });
    if (!label) startEditingLabel(id);
  }

  return {
    doneIds,
    userNotes,
    editingId,
    openNoteId,
    attachments,
    openAttachmentId,
    lastDeleted,
    workingDeadlines,
    isCustom: isCustomTask,
    toggleDone,
    commitLabel,
    openNote,
    commitNote,
    openAttachment,
    commitAttachment,
    deleteEntry,
    undoDelete,
    insertCustomTask,
    addTaskAtEnd,
    moveEntry,
  };
}
