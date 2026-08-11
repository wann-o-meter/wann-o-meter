## Correctness

- [x] Summary says _„Die nächste Frist ist am Do., 03.09.2026: Wohnung kündigen"_ but that task's Frist is 04.08.2026 and has passed. The summary is quoting the recovery date as if it were the deadline. Split the two: _„1 Frist verstrichen, 9 offen. Nachholen bis Do., 03.09.2026."_
- [x] Summary says _„10 Aufgaben, 10 noch offen"_ while one is overdue. Overdue is not the same state as open — it needs its own count, since it's the only state that requires action today.
- [x] Kündigung by 03.09 gives Mietende 30.11.2026 against a move on 16.10.2026 — six weeks of double rent. The plan computes both numbers and doesn't say this. That overlap is exactly the kind of derived insight a generic checklist can't produce.
- [ ] Timeline shows „möglich ab" capsules for some tasks; the cards never show a start date. Same data, two views, one of them silently dropping it.

## Consistency

- [ ] Three date formats on one screen: `Do., 03.09.2026` (summary), `Di, 04.08.2026` (card), `Fr, 16. Oktober 2026` (flag). Pick one long form and one short form and define where each is used.
- [x] The card rail (vertical line with hollow dots, left of the cards) reuses the timeline's exact visual vocabulary — hollow circle on a line — but its dots are evenly spaced by list order, not by date. Same glyph, different meaning. Either space the rail proportionally to date or change the glyph.
- [ ] Only two of ten markers have a „möglich ab" capsule. Verify this is real data and not a rendering condition that fails for tasks without an explicit start.
- [ ] Werktag and Wochenende cells in the day band are nearly the same value. The band's whole job is making weekday structure visible; widen the gap between those two fills.
- [ ] Month labels sit under the tick rather than centred in the month span, so „Aug" appears roughly above 20 August.
- [ ] The VORHABEN field is styled as a card like UMZUGSTAG and ORT but isn't interactive. Either make it a select (it's the natural place to switch Vorhaben) or demote it to a plain line of text.
- [ ] The page title already says _Umzug_, and the VORHABEN field repeats _Umzug innerhalb Deutschlands_. One of them can go.
- [x] Card 1 has no eyebrow; card 2 has _ALS NÄCHSTES_. An overdue card deserves the stronger eyebrow, not none.
- [x] Rail dot vertical alignment differs between the two cards (card 1 aligns to card top, card 2 to the eyebrow).

## Hierarchy

- [x] Inside card 1 the _Mietende_ segmented control is filled navy while the actual action _„Kündigung der Wohnung aufsetzen"_ is outlined. The setting looks more actionable than the action. Invert: segmented control as quiet toggle, one filled button.
- [x] Card 1 carries two provenance affordances — _▶ Wie berechnet?_ and _Grundlage: § 573c BGB ↗_. Fold the paragraph reference into the disclosure, or drop the disclosure and link the paragraph.
- [x] The headline asks _„wann muss ich anfangen?"_ and the page never answers it in those terms. With an overdue task the answer is _„Du bist spät dran"_ — that belongs above the timeline, not inferred from a red card further down.
- [ ] The legend row mixes two unrelated things: state keys (offen / erledigt / möglich ab) and band filters (Feiertage / Schulferien checkboxes). Separate them; filters are controls, keys are not.
- [ ] Overdue red appears in the timeline and on the rail but has no legend entry, despite being the most consequential state on this particular screen.
- [ ] Markers stack three deep at one x while long stretches sit empty. Worth checking whether lane packing is using the full occupied width including capsules, or only marker radius.

## Copy

- [x] _„möglich ab - Frist"_ and _„Frist verstrichen - bis 3. Sep nachholen"_ use hyphens where en dashes belong (– / —).
- [x] _„bis 3. Sep nachholen"_ abbreviates the month while every other date on the page is written out or numeric. Same fix as the date-format item.
- [x] _„Wie berechnet?"_ is missing a word. _„Wie wird das berechnet?"_ or just _„Berechnung"_.
- [x] The strikethrough on _Frist: Di, 04.08.2026_ implies the date is void, but it's the date that still governs the legal outcome. Consider keeping it upright and marking it _verstrichen_ instead.

## Accessibility and interaction

- [x] The round checkboxes next to task titles need visible labels or `aria-label`; as bare grey circles they also collide with the timeline's „offen" glyph.
- [x] The _Mietende_ control needs `role="radiogroup"` with proper checked state — segmented controls built from buttons are unreadable to screen readers.
- [ ] `▶` as a disclosure marker should be a real `<details>`/`<summary>` (or a button with `aria-expanded`), not a glyph.
- [ ] The Umzugstag label _„Fr, 16. Oktober 2026"_ runs to the container edge and will clip at narrower widths — needs the flip-to-`text-anchor: end` clamp.
- [ ] Check contrast of the grey month labels and legend text against the light blue background; they look under 4.5:1.
- [ ] If the header is sticky, confirm the _AUFGABEN_ section and each card have `scroll-margin-top` so marker → card jumps don't land underneath it.

The two I'd fix first are the summary sentence (it currently states something false) and the double-rent gap (it's the strongest demonstration on the page that this isn't a checklist).
