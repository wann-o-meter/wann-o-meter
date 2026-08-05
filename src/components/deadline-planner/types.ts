import type { Deadline } from "../../../lib/deadline-plan";

// Generic so a future Geburt/Hochzeit/etc vertical can reuse this outright -
// what a specific vertical would hardcode instead comes in as props.
export interface PlanVariant {
  slug: string;
  label: string;
  regionCode?: string; // fed straight to holidaysFor(), optional
  deadlines: Deadline[];
}
