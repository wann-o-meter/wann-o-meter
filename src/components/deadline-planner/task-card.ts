import type { Component } from "vue";

/** Only one inline editor can be open on a card at a time. */
export type EditorKind = "label" | "date" | "note" | "attachment";

/** Every commit from a card is the same shape: one field, one new value. */
export type TaskPatch = Partial<Record<EditorKind, string>>;

export type MenuItem = {
  label: string;
  icon: Component;
  danger?: boolean;
  onSelect: () => void;
};
