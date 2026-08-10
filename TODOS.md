# Open Todos

- [x] shorten the explanation texts
- [ ] on mobile the date selection on the start page is difficult because i scroll but i cannot really select the date in detail. it would be better to show a fixed window, e.g., a year from now and let the user scrub through
- [x] currently all "Vorhaben" are shown as a list but the user cannot select anything else which is irritating because the user thinks that there are other options to select from
- [x] the start page doesn't ask where only when but then a city is preselected. give the user the option to select a city by searching for it or use the current location and estimate the nearest city (Ort select added on the start page. Search and geolocation skipped, only 4 pilot cities exist and the data has no coordinates)
- [x] "als ICS exportieren" downloads the ics directly, add a download icon to indicate it. same applies to checkliste drucken, add a printer icon
- [x] on mobile the cards and the dates are a bit crammed. add a y-margin between them
- [x] "Trifft auf mich zu" show the options below the text
- [x] "Zurück zum Zeitstrahl" -> "Zurück zur Startseite"
- [x] on mobile fix the date popup when changing the date of a card. it keeps closing.
- [x] there is too many font types, sizes, weights, etc., On mobile it really gets messy. Consolidate this ![Messy mobile](mobile.png)
- [x] "Umzug/Hochzeit/... in deiner Stadt" is nice but it becomes messy if there are lets say 1500 cities
- [x] "Umzug" is preselected but you still have to click it to select the date
- [x] the checkbox for the main even in the list is looking weird
- [x] after placing the event on the timeline it cannot be reset without clicking the event type, e.g. Umzug which is bad UX
- [x] on mobile the top navbar and the top content has too much space such that the main content, meaning the events are almost hidden.
- [x] the ticks in the timeline don't align
- [x] on hover in the timeline show the date the mouse is on
- [x] the dots on the rail aren't centered
- [x] the pencil icon on the card implies that the user can change the text which it doesn't. change the icon to a note with a plus (StickyNotePlus) and add a way to edit the title of the task (MessageSquarePlus, lucide-vue-next 1.0.0 has no StickyNotePlus)
- [x] Kündigungsschreiben aufsetzen is a CTO but it's a button that opens a textbox whereas the reference to gesetze-im-internet is a link. there should be a better distiction between links and buttons
- [ ] add a small confetti effect when a task is done
- [ ] add localhost integration to save the progress of the tasks
- [ ] read through the review and fix the problems. after you're done, remove the review about the design.

## Review from Opus about the design

Looking at the screenshot, the typography is already better than most tools in this space — the mono/sans pairing gives it a "computed, verifiable" feel that fits the product. The problems are mostly about **rule consistency** and **hierarchy inversion**.

### 1. Make the mono/sans split a rule, not a vibe

Right now mono appears on labels (`VORHABEN`, `TRIFFT AUF MICH ZU`), on values (`21.01.2027`), on legends, and on prose-ish things (`Mittwoch · 90 Tage vorher`). Sans appears on other values (`Rottenburg am Neckar`, `Umzug innerhalb Deutschlands`). So within a single field row you get mono for one value and sans for the next.

Pick one axis and hold it. The one I'd choose:

> **Mono = machine-derived. Sans = human-written.**

- Mono: dates, day counts, `36 TAGE PUFFER`, `in 86 Tagen`, `§ 573c BGB`, month ticks, `HEUTE`.
- Sans: headings, field labels, legend, card titles, all explanatory prose.

That moves your small-caps labels to sans and makes the mono _mean something_ — every mono string on the page becomes "this was calculated." That's your whole product thesis.

### 2. Hierarchy is inverted

`Umzug: wann muss ich anfangen?` is roughly 48px and is the least useful text on the page — the user already knows what they clicked. Meanwhile `in 86 Tagen`, the actual answer, is ~12px, right-aligned, third line of a stack.

- H1 → 32–34px, weight 700 not 800, tracking `-0.02em`.
- Promote the countdown: 24–28px mono on the first upcoming deadline, with `4. November 2026` as the secondary line. One hero number per screen.
- Card title `Wohnung kündigen` → 18px/600. It's currently competing with the H1's weight at half the size.

### 3. Concrete scale

| Role                 | Size / line-height      | Face                |
| -------------------- | ----------------------- | ------------------- |
| H1                   | 33 / 1.15, -0.02em      | sans 700            |
| Hero countdown       | 26 / 1.2                | mono 600            |
| Card title           | 18 / 1.3                | sans 600            |
| Field value          | 17 / 1.4                | sans 500 / mono 500 |
| Body prose           | 16 / 1.55, max **68ch** | sans 400            |
| Rail date            | 15 / 1.3                | mono 600            |
| Labels, months, meta | 12 / 1.2, +0.06em       | sans 500 caps       |

The body copy in the Kündigung card currently runs ~110 characters per line. Cap the card text column, not the card.

### 4. Two specific bugs

- **`§ 573C BGB`** — you're applying `text-transform: uppercase` to the chip. Paragraph letters in German statutes are case-sensitive; `573c` and `573C` are not interchangeable, and a legal-adjacent product loses credibility on exactly this detail. Kill the transform on that chip.
- **Letterspacing on mono caps** is too wide (`Feiertage`, `Schulferien`, `36 TAGE PUFFER`). Mono is already generously spaced; adding `0.1em` makes it read as disconnected glyphs. `0.03em` max, and `0` for mono lowercase.

### 5. Smaller things

- Add `font-variant-numeric: tabular-nums` anywhere sans renders digits, so nothing shifts when 86 becomes 85.
- Collapse to a three-step grey ramp: `#1a1d21` body, `#5c6570` secondary, `#949aa2` labels. You currently have labels nearly as dark as prose, which flattens the whole form row.
- `5 von 7 Fristen sind noch nicht verifiziert.` should be 13px with an icon, not full body size — it's a caveat, and at current size it reads as a warning about the result rather than about data provenance.
- The legend checkboxes sit visually above the chart with no anchoring; 12px sans + a 8px color swatch instead of the current mono treatment will quiet them down.

## 6. Face pairing

If the mono is JetBrains Mono, its sans companion doesn't ship — you're pairing it with something geometric that has a different x-height, which is part of why the field row looks unsettled. Two options that solve it structurally: **IBM Plex Sans + IBM Plex Mono** (designed together, slightly bureaucratic tone that actually suits a deadline/§-heavy product), or keep your grotesk and switch mono to **Berkeley Mono / Commit Mono**, both of which have x-heights tuned to sit next to Inter-class sans.
