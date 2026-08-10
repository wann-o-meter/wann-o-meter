**Bugs**

- [x] Tooltip still renders over the Umzugstag flag and hides both the label and the date
- [x] Tooltip has no offset from the hovered dot — position it below the rail or to the side
- [x] "Wohnung kündigen" on 3 Sep is marked "Frist verstrichen" but sits _after_ today and after the move day — verify the expired comparison
- [x] The same card says "spätestens am 3. Sep nachholen" while being dated 3 Sep — the rescue date and the card date are identical, so the advice is circular
- [x] Sorting places the expired Kündigung last, after the move day — an overdue item should not appear at the end of the plan
- [x] Intro says "Die nächste offene ist am Di., 18.08.2026" but the first card is 21 Juli 2026 and is not struck through, so it reads as open
- [x] Only one month label ("Sep") visible on the entire rail

**Timeline**

- [x] Two overlapping past-markers remain (hatched block and grey bar) with different extents and no distinction
- [x] The lower grey bar ends mid-September for no visible reason
- [x] The blue horizontal bar right of the flag is still unlabelled
- [x] Toggles sit above the rail now but the rail has no legend at all — the four dot states (open, done, next, move day) are unexplained

**Card actions (image 3)**

- [x] Four icon-only buttons with no labels or tooltips — calendar, pencil, comment, X are all guessable but none are certain
- [x] The X reads as "close card" but presumably deletes the task — dangerous ambiguity, needs a label or confirmation
- [x] "Als Nächstes" is a status badge sitting in the same row as four action buttons, at similar size — separate status from controls
- [x] Five elements in the top-right corner is more chrome than the card content itself; move actions to a hover state or an overflow menu

**Umzugstag row**

- [x] Still an empty grey bar with a checkbox and one button — a milestone should not be checkable like a task
- [x] "Termin verschieben" here vs. the calendar icon on task cards are the same gesture in two forms

**Remaining density**

- [x] The expired card is still by far the tallest element on the page; compress it to title, one line, and the Mietende toggle
- [x] "Spätester Kündigungstermin nach § 573c Abs. 1 BGB" still duplicates the § 573c chip below it
- [x] Gutter shows "6 Wochen vorher" / "2 Wochen vorher" again on some entries but not others — apply consistently or remove
