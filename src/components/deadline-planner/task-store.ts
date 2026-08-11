import type { ScheduleEntry } from "../../../lib/deadline-plan";
import type { EditorKind, TaskPatch } from "./task-card";

/**
 * Everything a card needs in order to read and write its own task, bundled
 * so the rail takes one prop instead of eleven. Built in DeadlinePlanner from
 * useTaskEditor; nothing here is new state.
 */
export type TaskStore = {
  doneIds: Record<string, boolean>;
  userNotes: Record<string, string>;
  attachments: Record<string, string>;
  isCustom(id: string): boolean;
  editorFor(id: string): EditorKind | null;
  setEditor(id: string, kind: EditorKind | null): void;
  applyPatch(entry: ScheduleEntry, patch: TaskPatch): void;
  deleteEntry(entry: ScheduleEntry): void;
};
