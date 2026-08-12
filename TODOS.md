# Wann-O-Meter — UI todos

## Correctness (do first)

- [x] Reconcile the two move dates: the Vorhaben card says 28.10.2026, the planner is set to 10.11.2026 — decide whether the planner edits the existing Vorhaben or creates a new one, and make that explicit
- [x] Reconcile the four conflicting counts: "12 offene Fristen", "0/12", "6 weitere Fristen später", "10 Fristen"
- [x] Make it unambiguous which date each count is derived from

## Page structure

- [x] Collapse the "Was hast du vor?" onboarding block once a Vorhaben exists — replace with a "Weiteres Vorhaben planen" affordance
- [x] Hide the 1-2-3 stepper for returning users
- [x] Move the Vorhaben card above the deadline list, or place it beside the list to use the empty right-hand gutter
- [x] Reduce the wide empty column on the right at desktop widths

## Deadline list

- [x] Hide the "Umzug" category column while only one Vorhaben exists
- [x] Collapse the date + "in X Tagen" pair — keep the countdown primary, the absolute date secondary
- [x] Remove duplicate overdue signals in the overdue row (section header + red date + "abgelaufen" — keep one)

## Task cards

- [x] Demote the "Bis Donnerstag, 3. September 2026 nachholen." line so the task title stays the strongest element in the card
- [x] Pick one date-format rule (long form for the actionable deadline, short form for derived dates) and apply it consistently
- [x] Shorten CTA labels so they don't restate the card title ("Kündigung aufsetzen", not "Kündigung der Wohnung aufsetzen")
- [x] Use one verb across all cards for the same action ("aufsetzen" vs. "bearbeiten")
- [x] Limit filled primary buttons to one per screen; outline for the rest
- [x] Give the footer rail one job — controls above the divider, provenance ("Grundlage: …") always below
- [x] Show provenance on all cards or none
- [x] Move the "Wie wird das berechnet?" disclosure below the CTA

## Typography and color

- [x] Define one rule for monospace (e.g. hard dates only) and apply it everywhere
- [x] Fix mono inconsistencies: "Nächste Frist: … 16.09.2026" and "erste am Do., 03.09.2026" are sans while equivalent dates are mono
- [x] Decide whether mono applies to status badges at all
- [x] Reduce to two accent colors plus neutral; drop accents that carry no meaning

## Timeline

- [ ] Add a legend or labels for the circle markers
- [ ] Explain the stacked lane rows, or flatten them
- [ ] Label the blue/beige/gray bar segments, or remove the color coding
