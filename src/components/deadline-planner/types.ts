import type { Deadline } from "../../../lib/deadline-plan";
import type { Component } from "vue";

export interface PlanVariant {
  slug: string;
  label: string;
  regionCode?: string; // fed straight to holidaysFor(), optional
  deadlines: Deadline[];
}
