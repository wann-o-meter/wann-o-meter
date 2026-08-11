import type { Deadline } from "../../../lib/deadline-plan";

export interface PlanVariant {
  slug: string;
  label: string;
  regionCode?: string;
  deadlines: Deadline[];
}
