import { onBeforeUnmount, onMounted, ref } from "vue";

type TaskPickerTarget = { kind: "end" };

export type TaskPicker = ReturnType<typeof useTaskPicker>;

export function useTaskPicker(handlers: {
  addAtEnd(label: string, date: string): void;
}) {
  const target = ref<TaskPickerTarget | null>(null);

  function isOpen(candidate: TaskPickerTarget): boolean {
    return target.value?.kind === candidate.kind;
  }

  function toggle(candidate: TaskPickerTarget) {
    target.value = isOpen(candidate) ? null : candidate;
  }

  function close() {
    target.value = null;
  }

  function pick(label: string, date: string) {
    if (!target.value) return;
    handlers.addAtEnd(label, date);
    close();
  }

  function onClick(event: MouseEvent) {
    if (!target.value) return;
    const el = event.target as HTMLElement | null;
    if (el?.closest(".task-add, .add-end")) return;
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
