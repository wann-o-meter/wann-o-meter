import { onBeforeUnmount, onMounted, ref } from "vue";

/** Which "+" is open: a gap between two tasks, or the end-of-list button. */
export type TaskPickerTarget =
  | { kind: "gap"; id: string; afterOffset: number; beforeOffset: number }
  | { kind: "end" };

export type TaskPicker = ReturnType<typeof useTaskPicker>;

export function useTaskPicker(handlers: {
  insertInGap(afterOffset: number, beforeOffset: number, label?: string): void;
  addAtEnd(label?: string): void;
}) {
  const target = ref<TaskPickerTarget | null>(null);

  function isOpen(candidate: TaskPickerTarget): boolean {
    const t = target.value;
    if (!t || t.kind !== candidate.kind) return false;
    return t.kind === "gap" && candidate.kind === "gap"
      ? t.id === candidate.id
      : true;
  }

  function toggle(candidate: TaskPickerTarget) {
    target.value = isOpen(candidate) ? null : candidate;
  }

  function close() {
    target.value = null;
  }

  function pick(label?: string) {
    const t = target.value;
    if (!t) return;
    if (t.kind === "gap")
      handlers.insertInGap(t.afterOffset, t.beforeOffset, label);
    else handlers.addAtEnd(label);
    close();
  }

  // No backdrop, so these close it on outside click / Escape. Escape is
  // document-level, not @keydown.esc on the popover: focus sits on the trigger
  // button, a sibling, not an ancestor, so the popover would never see the
  // bubbled key.
  function onClick(event: MouseEvent) {
    if (!target.value) return;
    const el = event.target as HTMLElement | null;
    if (el?.closest(".task-picker, .gap-add, .add-end")) return;
    close();
  }
  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && target.value) close();
  }

  onMounted(() => {
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeydown);
  });
  onBeforeUnmount(() => {
    document.removeEventListener("click", onClick);
    document.removeEventListener("keydown", onKeydown);
  });

  return { target, isOpen, toggle, close, pick };
}
