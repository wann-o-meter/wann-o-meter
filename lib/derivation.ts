// The vocabulary a worked-out Frist speaks, shared by the two ways one gets
// computed: a CalendarRule spelled out in yaml, and the handful of Fristen whose
// statute needs real code and therefore has a file next to its yaml.

export interface DerivationStep {
  step: string;
  label: string;
  value?: string;
}

// What a Frist with its own file hands back. Everything past `date` is optional
// because it is the statute that decides whether there is more to say.
export interface FristSolution {
  date: string;
  derivation?: DerivationStep[];
  // The deadline for the date the visitor asked about has already passed.
  pastDeadline?: boolean;
  // The next date that is still reachable, when the asked-for one is not.
  rescue?: { date: string; label: string } | null;
  // How long the old contract still runs past the anchor.
  leaseEnd?: { date: string; overlapDays: number };
}

// anchorDate is the day the visitor gave. today is passed in rather than read
// so the same input always produces the same output in a test.
export type FristSolver = (
  anchorDate: string,
  countryCode: string,
  regionCode: string | undefined,
  today: string,
  deferMonths: number,
) => FristSolution;
