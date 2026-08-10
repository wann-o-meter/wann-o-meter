**Bugs**

- [x] Every task date is a Sunday (27 Sep, 25 Okt, 1 Nov, 8 Nov) — the offsets are being applied in whole weeks from a Sunday move date, so no task ever lands on a weekday
- [x] Consequently the "Sa/So, Ämter haben zu" warning fires on almost every card — fix the root cause instead of offering "vorziehen" everywhere

**Homepage**

- [x] The numbered "1. Datum wählen · 2. Fristen sehen · 3. Als Kalender exportieren" row still sits at the bottom, after the user has already done step 1 — move it up
- [x] "ORT" now sits _below_ the timeline and summary, so the plan is computed before the location is chosen — move it next to the date
- [x] Timeline spans 13 months while all activity is in a 3-month window — clip the range to the plan plus a small margin
- [x] "Zeitplan öffnen" floats over the rail and covers it; place it below the summary line
- [x] Summary line "So., 08.11.2026 · 10 Fristen · erste am Do., 03.09.2026" repeats the date already shown in the field and the flag

**Detail page timeline**

- [x] Legend has grown back to seven items across two visual languages — trim to the toggles plus at most two states
- [x] "möglich bis Frist" swatch is a pill shape; the same element on the rail is a thin bar — make them match
- [x] Two past-markers still overlap (grey rail band and the darker bar below), ending at different points
- [x] Sticky timeline overlaps the top card so its title is cut off — add scroll padding

**Cards**

- [x] Same-day tasks (25 Okt group) show the date only on the first card, so the following ones look undated
- [x] "Auf 23. Okt vorziehen" and "Auf 30. Okt vorziehen" appear as primary-weight buttons inside otherwise calm cards
- [x] "Kündigungsschreiben aufsetzen" appears on two different cards with identical styling but presumably different targets
- [x] Card borders alternate between plain and blue-outlined with no visible rule — clarify what the outline means
