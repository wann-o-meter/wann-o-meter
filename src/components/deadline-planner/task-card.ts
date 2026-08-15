import type { Component } from "vue";

export type EditorKind = "label" | "note" | "attachment";

export type TaskPatch = Partial<Record<EditorKind, string>>;

export type MenuItem = {
  label: string;
  icon: Component;
  danger?: boolean;
  onSelect: () => void;
};
