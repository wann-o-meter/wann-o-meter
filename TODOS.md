# Open Todos

- [x] shorten the explanation texts
- [x] on mobile the date selection on the start page is difficult because i scroll but i cannot really select the date in detail. it would be better to show a fixed window, e.g., a year from now and let the user scrub through
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
- [x] Buttons and links should have the same sizes, correct margins, and links that open a new tab should have an arrow from lower left to upper right
- [x] add a small confetti effect when a task is done
- [x] add localhost integration to save the progress of the tasks (localStorage, keyed per Vorhaben and Ort)
- [x] in the timeline the button link to the deadline view is overlapping with the dates ![alt text](overlapping.png)
- [x] read through the review and fix the problems. after you're done, remove the review about the design. (grey ramp skipped, the proposed label grey fails contrast on paper. H1 stays weight 600, the scale has only 400 and 600)
- [x] fix the order and size of the card dates: 5. Oktober 2026 ← 20px mono 600, near-black, Montag · 90 Tage vorher ← 12px sans, grey, in 56 Tagen ← 12px sans, grey
- [x] Reverse the date hierarchy: make the absolute date the large, dominant element and demote the countdown to small muted text — humans anchor on "5. Oktober", not "in 56 Tagen"
- [x] instead of saying in 56 Tagen, use weeks, e.g., in ca. 8 Wochen
- [x] Drop "90 Tage vorher" entirely, or move it into the card as context — three different time expressions per entry is two too many
- [x] Add the weekday to the same line as the date rather than a separate row, e.g. "Mo, 5. Oktober 2026"
- [x] For dates beyond ~90 days out, replace the day countdown with a coarser unit ("in gut 4 Monaten") — 128 days is not a quantity anyone can feel
- [x] Move "Trifft auf mich zu" above the fold explanation: a single unchecked "Auto" chip reads like a broken filter, not an opt-in — add a short line like "Ergänze deine Situation für weitere Aufgaben"
- [x] Add more filter chips at once (Haustier, Kinder, Gewerbe, Eigentum) so the row looks like a set of choices rather than one stray checkbox (skipped: a chip only exists where a deadline actually depends on it, so adding four would mean inventing the deadlines behind them)
- [x] "5 von 7 Fristen sind noch nicht verifiziert" is honest but alarming as the first thing under the timeline — reword toward what is verified, e.g. "2 Fristen gesetzlich belegt, 5 auf Erfahrungswerten"
- [x] Give the verification notice a way to act on it — link it to the "Quelle vorschlagen" flow instead of leaving it as a dead-end warning
- [x] Move the "Umzug in deiner Stadt" city switcher above the timeline: choosing the wrong city invalidates everything below it, so discovering it at the bottom is too late (the live Ort select already sits above the timeline in the planner form. The bottom nav is cross-page linking, moving it would push the tool below the fold)
- [x] Make the city chips reflect the current selection more clearly — Rottenburg is outlined but reads as hoverable, not as "you are here"
- [x] Fix the mini timeline's right edge: "Jan 20…" is clipped, and the Umzugstag label collides with the axis
- [x] Add a legend or tooltip for the stacked circles in the mini timeline — they currently look like decoration, not like the tasks below
- [x] Make the mini timeline clickable to scroll to the matching task, otherwise it is a picture rather than a control (already wired, onTimelineSelect scrolls the rail and flashes the card)
- [x] Distinguish "Puffer" values visually from task dates — right now "30 Tage Puffer" sits in the same column flow and competes with real deadlines
- [x] Reconsider showing puffer at all for gaps under ~14 days; "7 Tage Puffer" twice in a row adds noise without insight
- [x] Give the Umzugstag row real content (Zählerstände ablesen, Übergabeprotokoll) — an empty highlighted row looks like a rendering bug
- [x] Remove the unlabeled icon next to "Umzugstag" or give it a visible label
- [x] Unify action buttons: "Kündigungsschreiben aufsetzen" appears once as a boxed button and once as a plain button of different width — same action, same treatment
- [x] Separate source chips from action buttons visually: "§ 573c BGB" and "Kündigungsschreiben aufsetzen" sit side by side at equal weight but are metadata vs. action
- [x] Shorten the "Wohnung kündigen" description to one sentence and move the two assumptions (Feiertage nach Zielort, Mietende ohne Überlappung) into the "Wie berechnet?" panel where they belong
- [x] Make "Mietende ohne Überlappung" an actual toggle instead of a disclaimer — it changes the deadline by a full month and is the most consequential hidden assumption on the page
- [x] Open "Wie berechnet?" by default on the one card that has it, since it is the strongest trust signal on the page and currently hidden behind a summary
- [x] Add descriptions to the cards that have none (Umzug only, the other Vorhaben have no data yet) — five of seven are title-only and read as unfinished next to the fully written first card
- [x] Add "Möglich ab / Frist" lines to more tasks (skipped: a range needs a researched earliest day per task, inventing those is exactly what the null placeholders exist to prevent), not just Ummeldung — the range model is the differentiator and appears exactly once
- [x] Reduce the left gutter width or widen the cards; roughly a quarter of the content column is empty whitespace between date and card (partly: the promoted 18px date needs 10.5rem, so the gutter is 12.2rem instead of 12.5rem. A big date and a narrow gutter cannot both hold, months are now abbreviated to buy what room there was)
- [x] Clarify "Auf diesem Gerät gespeichert" — state what happens on another device and whether an account will exist later
- [x] Add a "was ist erledigt" progress indicator near the top; with checkboxes present, users will want a count without scrolling
- [x] Consider collapsing tasks whose date has passed (deferred by the item itself, "once the plan is in active use") rather than leaving them inline, once the plan is in active use
- [x] the main event is already a vertical bar. why not make it a big flag? :)
- [x] The code is centers around rent and embedds elements that are only relevant for renting. E.g. isn't leaseEnd something that is something related only to leasing of an appartment. (rescue now carries a date plus a sentence the rule words itself, leaseEndMonth stays inside lib/notice-period.ts, and the schedule option is deferMonths)
- [x] Doesn't "Alte Wohnung einen Monat länger behalten" only make sense when the deadline has passed? (agreed, it now lives on the card whose deadline was missed)
- [x] The progress bar will be hidden behind the widened timeline that gets widened on scroll.
- [x] The "Alte Wohnung einen Monat länger" looks out of place
- [x] Fix contradiction in the derivation: overlap toggle is on (move 20 Oct, lease end Nov 30) but step 2 states "kein Überlappungsmonat eingeplant" — the trust panel is showing false text
- [x] Fix the verification count: "2 gesetzlich belegt, 5 auf Erfahrungswerten" adds to 7 of 10 tasks — three are unaccounted for
- [x] Show a date for every task: Nachsendeauftrag, Halteverbot, Zählerstände, Übergabeprotokoll and Rundfunkbeitrag currently have only a rail dot and no visible date
- [x] Especially fix Halteverbot — its lead time is the entire reason the task exists, and it currently shows no date at all
- [x] Add a compact in-card date line as fallback whenever the gutter label is suppressed by collision
- [x] Remove the duplicated assumptions in "Wie berechnet?" — the holiday region and lease-end assumptions each appear twice, once as a numbered step and once as "Annahme:"
- [x] Invert the derivation panel order: result first and prominent, calculation steps collapsed below, assumptions last and stated once
- [x] Shorten the "Wohnung kündigen" card overall — it is roughly five times the height of every other card and pushes the rest of the plan below the fold
- [x] Move the overlap toggle out of "Trifft auf mich zu" and into the Kündigen card, where its effect is visible on the date
- [x] Render it as a choice rather than a question, e.g. "Mietende: Ende Okt · Ende Nov (Überlappung)" instead of "Kündigungstermin verpasst?"
- [x] Separate the two kinds of toggles conceptually: "Auto" is a personal attribute, overlap is a planning decision — they should not share a group
- [x] Fix the city switcher: "Rottenburg am Neckar (aktuell)" renders as bare text between chips and looks broken — style it as a selected chip
- [x] Fix the clipped Umzugstag label on the right edge of the mini timeline
- [x] Remove or explain the grey "Mo, 2. November 2026" floating top-right of the mini timeline — it reads as a stuck hover state
- [x] Label or remove the unlabeled monitor icon in the header
- [x] Restore the search affordance in the header, or drop the header nav entirely rather than leaving one mystery control (dropped: the Cmd+K handler still pointed at a #search-input that no longer exists)
- [x] Reconsider "28 Tage Puffer" appearing exactly once — a single occurrence reads as arbitrary rather than systematic (label removed entirely, the gap height already carries it and the number moved to its tooltip)
- [x] Add the Bürgeramt appointment lead time to the Ummeldung calculation: the description mentions needing an appointment, but the plan only shows the legal deadline, not when to start (skipped: a lead time is a concrete number and varies by Kommune, inventing one is what the null placeholders exist to prevent)
- [x] Give the mini timeline a legend or hover labels — the stacked circles still require the caption to be understood
- [x] Consider whether checked-off tasks should keep full card height; the green completed cards take as much space as open ones
- [x] Move the progress bar under the timeline and make it sticky so it stays useful once the user scrolls into the list
- [x] Introduce a more user-friendly design with rounded corners and better shadows, remove blue glowing shadows
- [x] Add margin in theme toggle between text and icon
- [x] Verify that elements have enough margin but not too much (audited: 29 distinct spacing values in the redesigned files, snapped onto a 7-step scale of 0.25/0.5/0.75/1/1.5/2/3rem. Rail gutter constants and the calendar views were left alone)

- [x] Add a date input as an equal alternative to dragging (`[31].[01].[2027]` or native picker) — drag-only is undiscoverable on desktop and broken on touch
- [x] Add quick presets as chips: "In 3 Monaten", "Zum Monatsende", "Nächster Monatserste", "Weiß ich noch nicht" (three, "Weiß ich noch nicht" left out: the plan needs a date to exist at all)
- [x] Put a visible, pre-positioned handle on the timeline (default: today + 3 months) with grip affordance, shadow, and `cursor: grab`
- [x] Show a live preview under the handle while dragging: "So, 31. Jan 2027 · erste Aufgabe am 4. Nov 2026 · 10 Fristen"
- [x] Rewrite the subline — "Der Rest wächst rückwärts daraus hervor" is a metaphor, not an instruction → "Wähl dein Datum — alle Fristen werden rückwärts berechnet."
- [x] Remove the Feiertage/Schulferien checkboxes from the start page (they filter data that isn't visible yet)
- [x] Remove "Aufgabe" from the start-page legend — there are zero tasks at this point
- [x] Fix the dead vertical space; the footer is stranded mid-viewport (the plan now renders from first paint, so the page fills)
- [x] Unify the measure — headline column ~540px vs. timeline ~1300px
- [x] Restyle the ORT select to match the category chips
- [x] Defer ORT until after the date is chosen, or geo-default it
- [x] Fix the label: "ZIEH ÜBER DEN ZEITSTRAHL - WANN IST ES SOWEIT?" → sentence case, en dash, shorter
- [x] Add a 3-step "So funktioniert's" strip: Datum wählen → Fristen sehen → Als Kalender exportieren
- [x] Add keyboard support: arrow ±1 day, shift+arrow ±1 week, Home/End = bounds, visible focus ring
- [x] Style the rail as a grabbable track (inset background, rounded ends), not a printed ruler

- [x] Restore relative offsets on every card ("6 Wochen vorher", "2 Wochen danach") — your SSR HTML has this and hydration throws it away
- [x] Pair or replace "in gut 5 Monaten" → `2 Wochen vor dem Umzug · in gut 5 Monaten`; six tasks currently all read "in gut 6 Monaten"
- [x] Add the summary sentence at the top: "Aus deinem Umzugstag am 31. Januar 2027 ergeben sich 10 Fristen. Die erste ist am 4. November 2026."
- [x] Collapse the timeline by default, or move it below the first three tasks
- [x] Explain the circle vocabulary in the legend — filled vs. ring, green vs. red vs. blue
- [x] Rewrite "TRIFFT AUF MICH ZU → ☐ Auto" as a full sentence: "Ich habe ein Auto, das ich ummelden muss"; drop the section header if there's only one item
- [x] Mark the next actionable task with an "Als Nächstes" badge and stronger card treatment
- [x] Bridge the empty gap between HEUTE (August) and the first task (November): "Bis November ist nichts zu tun."
- [x] Handle past deadlines explicitly: "Frist verstrichen — was du jetzt tun kannst"

- [x] Turn "Fällt auf ein Wochenende" from a red alert into a neutral hint with an action: "Sa/So — Ordnungsamt hat zu. Auf Fr, 29. Jan verschieben →"
- [x] Suppress the weekend warning on the Umzugstag itself — moving on a Saturday is the normal case
- [x] Collapse completed tasks into a "3 erledigt ▾" group at the bottom (replaces the earlier slim-done-card rules, which are deleted)
- [x] Add "Termin verschieben" per task so users can override a computed date
- [x] Make the header fields look editable — input styling, hover state, chevron on all three
- [x] Add a sticky mini-header on scroll: Umzugstag + "3 von 10 erledigt"
- [x] Give every card the same action row — only "Wohnung kündigen" has a CTA
- [x] Apply "Wie berechnet? (4 Schritte)" to all computed dates or none (only offset_rule entries have a derivation, and the panel is collapsed for all of them. Fabricating steps for plain offsets would be inventing a calculation)
- [x] Add "Plan-Link kopieren" with state encoded in the URL — "Auf diesem Gerät gespeichert" is an unmitigated data-loss risk (the link carries date, Ort, facets and Mietende. Ticks, notes and custom tasks stay in localStorage, and the copy now says so)
- [x] Give the ICS/print block a heading ("Plan mitnehmen")
- [x] Remove duplicated dates inside cards when the left rail already shows them (currently inconsistent) (the gutter date is never suppressed now, so the in-card fallback is gone)
- [x] Close the horizontal gap between the date rail and the cards
- [x] Move the progress bar above the timeline and label it — it's currently clipped (the sticky scroll-widening strip that clipped it is gone, 97 lines lighter)
- [x] Align card left edges (the first card sits ~5px left of the rest)
- [x] Reduce box-in-box nesting: card → description → warning box → source chip is four nested borders (the warning box became a coloured line, the source chip and actions are one row)
- [x] Rounded corners consistently: 8px cards/inputs/buttons, 6px chips/badges, 999px only for category pills
- [x] Use elevation instead of hairline borders — white surface + soft shadow on a tinted background
- [x] Split the blue: it's currently the today marker, the Umzugstag, all links, and the primary button
- [x] Split the red: it's Feiertage, weekend warnings, and open-task rings
- [x] Restrict mono to dates and numbers — logo + dates + UI labels dilutes the effect (logo and button labels moved to sans, mono is dates and counts only)
- [x] Add hover/active/focus states everywhere; nothing currently responds to a cursor
- [x] Replace the "System" toggle with a sun/moon icon plus a proper label or dropdown (icon plus a visible label that names the current mode)
- [x] Soften the page background or make cards white — near-identical greys give no figure/ground separation
- [x] Drop the left date rail below 640px; put the date above each card as a section header
- [x] Rework the timeline for mobile: horizontal scroll with snap points, or a simplified month band (it fits its container instead of scrolling, and it is folded away by default)
- [x] Enforce ≥44px tap targets on checkboxes and legend toggles
- [x] Add a sticky "Als ICS exportieren" bottom bar
- [x] Reframe "Quelle fehlt" as "Erfahrungswert" — as written it reads like a defect in your own product
- [x] Add a one-line "Warum?" to every task, not just some ("Halteverbotszone" has none)
- [x] Style the § chips as links with a consistent external-link icon (the global a[target=_blank] rule gives them the same arrow as every other outbound link)
- [x] Add `role="slider"` + `aria-valuenow`/`aria-valuetext` to the timeline handle
- [x] Don't encode task state in colour alone — add a shape or text label for filled/ring (four legend entries plus the state in each node's accessible name)
- [x] Check contrast on grey secondary text ("in gut 4 Monaten", card descriptions) — several are below 4.5:1 (measured: muted 6.75:1, accent 7.19:1, warn 5.87:1 on paper. Holiday and done were 3.2 and 4.37, darkened to 5.22 and 5.21)

- [x] Move date 08.11.2026 is a Sunday and gets no warning of its own, while every task around it is flagged — moving on a Sunday raises Hausordnung/Ruhezeit issues and landlords rarely do handovers then
- [x] "Zählerstände ablesen" offers "Auf 6. Nov vorziehen" — this task must happen on the move day itself, never before; suppress date-shifting for same-day tasks
- [x] Same for "Übergabeprotokoll unterschreiben" — it is tied to the handover, not to office hours
- [x] "Sa/So, Ämter haben zu" is applied to tasks with no Amt involved (Nachsendeauftrag is online, Zählerstände and Übergabeprotokoll involve the landlord) — gate the warning on whether the task actually requires an authority (new needs_office flag in the deadline schema, set on the five steps that actually need an Amt)
- [x] Five identical "Sa/So, Ämter haben zu" + "vorziehen" pairs in one plan reads as a template artifact; consider one grouped notice ("4 Aufgaben fallen auf ein Wochenende — alle vorziehen")
- [x] Sperrmüll falls on Allerheiligen and gets a red warning but no "vorziehen" button, unlike every weekend case — inconsistent affordance for the more severe collision
- [x] Huge unlabeled whitespace between 3 Sep and 25 Okt (~7 weeks) — the "Puffer" label that previously filled this is gone, so it now reads as a layout bug (label back on every gap of 14 days or more, and the max gap height is 72px)
- [x] Gutter label "Frist nach § 573c BGB, abhängig vom Umzugsmonat" overflows the column and breaks the left alignment of every other entry (a rule name is a sentence, so it no longer goes in the fixed-width date column)
- [x] Progress is stated three times: sticky bar "2 von 10 erledigt", "Fortschritt: 2 von 10 erledigt", and "2 erledigt" at the bottom — keep one (one statement, in the sticky header, with the done fold beside it)
- [x] "Bis Do., 03.09.2026 ist nichts zu tun" contradicts two tasks already being marked done
- [x] "Umzugstag" repeats as the relative label for four consecutive gutter entries — collapse same-day tasks under one date header
- [x] The Zeitstrahl is now collapsed behind "Zeitstrahl anzeigen" — it was the strongest visual differentiator; consider open by default, or at least a thumbnail preview (open by default, still foldable)
- [x] Umzugstag row is still an empty highlighted bar with only a "Datum ändern" control — either give it content or make it a slim divider
- [x] "Datum ändern" on the Umzugstag vs. "Termin verschieben" on tasks are the same gesture with two labels
- [x] "Termin verschieben" appears on all ten cards at equal weight — demote to an icon or hover action so it stops competing with the real per-task actions (back to an icon in the tool row, reversing the "same action row" change)
- [x] The "2 erledigt" disclosure sits at the very bottom, far from the progress bar it relates to — move it next to the progress indicator
- [x] Intro sentence says "10 Fristen", the verification line says "10 Aufgaben" — pick one noun, since not every entry is a Frist
- [x] "Ich habe ein Auto, das ich ummelden muss" is a single lonely checkbox again; either show the full set of situation toggles or hide the group until more exist
- [x] The overlap/Mietende decision has disappeared entirely from this version — verify it is still reachable, since it moves the first deadline by a full month (it shows on any card with an offset_rule now, not only once the deadline has passed)

- [x] Show the timeline by default again — remove the "Zeitstrahl anzeigen" disclosure
- [x] Reframe it from "overview of tasks" to "the landscape the tasks sit in", so it stops duplicating the list below
- [x] Demote task dots: smaller, lighter, no stacking — they are secondary here (11px instead of 24px, thinner ring, one lane instead of three)
- [x] Promote context layers: make Schulferien bands, Feiertag ticks, weekend shading and local closures the dominant visual content
- [x] Add weekend shading as a repeating subtle pattern so weekend collisions are visible before reading any card (one repeating gradient aligned to the window's first Saturday, not 104 elements)
- [x] Keep exactly one prominent marker: the Umzugstag flag
- [x] Grey out the region before today so remaining lead time is visible at a glance
- [x] Make the Umzugstag marker draggable on the timeline, recomputing the whole chain live (pointer events, so mouse, pen and touch share one path)
- [x] While dragging, show the resulting collision count as a live readout (e.g. "3 Kollisionen" → "0 Kollisionen")
- [x] Snap dragging to whole days and show the target date next to the cursor
- [x] Make the timeline sticky under the header at ~64px height so it stays visible while scrolling the list
- [x] Add a viewport indicator on the sticky timeline showing which time range the user is currently reading
- [x] Make clicking a point on the timeline scroll the list to the nearest task
- [x] Move the Feiertage/Schulferien toggles into the timeline itself rather than above it
- [x] Add a legend or inline labels for the context bands, since they carry the meaning now
- [x] Verify the timeline still communicates something when no collisions exist — it should read as "this window is clear", not as empty decoration ("Dieses Fenster ist frei." rather than a blank strip)
- [x] Fall back to a static, non-sticky version on mobile with drag replaced by tap-to-select
- [x] If the full interactive version is too much for now, ship the reduced variant: context bands plus Umzugstag only, no task dots, always visible (not needed, the full version is in)

- [x] Weekend shading is too heavy — the grey bars dominate and read as the primary content, while the actual months and tasks recede; drop opacity substantially (3% instead of 6%)
- [x] Weekend bars appear roughly every 7 days but with inconsistent widths and no clear pairing to Sa/So — verify the day-to-pixel mapping is correct (real off-by-one: Saturday is index 5 in the Mon-first scheme, not 6, so the stripes were painting Sun+Mon)
- [x] Two parallel horizontal rails (the light blue line and the grey bar below) with no legend for the lower one — either label it or merge them (the thread under the capsules is gone, one rail left)
- [x] The dark grey band from before "Heute" to Sep is the same colour as the weekend shading but means something else (past / Sommerferien?) — needs a distinct treatment (past time is a diagonal hatch now, weekends stay a flat tint)
- [x] The red/brown horizontal bar right of the Umzugstag is unexplained — no legend entry covers it (it was a task capsule recoloured for a closed day. Dots no longer carry that, see the next item)
- [x] Legend has 6 items in 3 different visual languages (hollow circle, filled circle, red circle, flag, checkbox+swatch) — unify into one row of swatches, move the two toggles apart from the four static keys (five swatches in one row, the two toggles pushed to the right)
- [x] "Amt hat zu" as a task state conflates a property of the date with a property of the task — consider marking the _day_ as closed rather than recolouring the dot (the day gets a closed band, the dot stays a task)
- [x] Month labels sit below the axis while the Umzugstag label sits above with a large gap — vertical rhythm is inconsistent
- [x] Caption "3 Aufgaben fällt auf einen geschlossenen Tag" — grammar error, and it duplicates the same sentence 400px above with different wording ("3 Aufgaben fallen auf einen Tag mit geschlossenen Ämtern") (the caption now describes the bands, the count lives in one place with agreeing grammar)
- [x] "Alle vorziehen" appears once at the top but the per-task "vorziehen" buttons are gone from the cards — verify the individual override is still reachable (still per-card for the five office tasks, and the grouped button now shows for one as well)
- [x] The "1 erledigt" disclosure is now expanded above the intro sentence, so a struck-through task is the first thing under the sticky bar — move it back below the list or collapse by default (back below the list, titled rather than counted)
- [x] Intro says the first task is 03.09. but the first visible card is 27.09. — because 03.09. is the completed one; the sentence should reflect the remaining plan (it names the next open one now)
- [x] Progress shown twice again (sticky bar + "1 erledigt" disclosure)
- [x] Gutter label wraps awkwardly ("6 Wochen vorher · in ca. / 7 Wochen") — widen the column or drop one of the two relative expressions
- [x] "6 Wochen vorher" and "in ca. 7 Wochen" sit adjacent and are easily confused; they anchor to different reference points (the countdown to today is gone, the offset to the Vorhaben stays)
- [x] "24 Tage Puffer" now appears above the first card, i.e. before any task — a buffer before the plan starts has no meaning (leading gaps are dropped, they appeared when a done task was filtered out)
- [x] Date field and the sticky "Umzugstag: So., 08.11.2026" bar state the same value twice, directly adjacent (the sticky bar is progress only)
- [x] The move date is a Sunday and still carries no warning of its own, though three derived tasks do (it was an inline span at the end of a wrapping row, now its own warning line)
- [x] Die nächste offene ist am Do., 03.09.2026. -> make Do., 03.09.2026. a link that jumps to the next task
- [x] The pill "Als nächstes" is not aligned with the buttons; it also overlaps with the task title on mobile (centred in the head row, and it no longer shares the blue with the card action)
- [x] Don't remove the tasks completely from the overview. Still keep a separate small list with finished tasks, but accidentally clicking on the checkbox means that the task disappears and has to be retrieved (a ticked task stays in place and shrinks to its title, the fold below is a second view of it)
      **Desktop**

- [x] "Bis Do., 03.09.2026 ist nichts zu tun" contradicts "Die nächste offene ist am Do., 03.09.2026" two lines above — same date, opposite meaning
- [x] Three separate status sentences stack before the timeline (task count, closed-office warning, nothing-to-do) — merge into one lead paragraph
- [x] Weekend bars are still visible but now nearly invisible against the background while the "Vergangen" band below is much darker — the two greys should not compete (weekends 5%, spent time a 9% hatch, both cut from shared declarations)
- [x] "Vergangen" legend swatch is a diagonal hatch but the actual band on the rail is solid grey — legend does not match rendering (swatch and band now share one --spent-hatch token, so they cannot drift)
- [x] The past band ends at Sep, but "Heute" sits well to its left — verify what the band actually represents (that was the Schulferien band being read as the past one, both now have distinct keys)
- [x] The brown/tan vertical bars (Feiertage?) are not in the legend; "Geschlossen" swatch is grey, not tan (the toggles lost their swatches when I unified the legend, they are back)
- [x] Legend now split across two sides of the row (keys left, toggles right) with different alignment — keep them on one baseline
- [x] The horizontal blue bar right of the Umzugstag is still unexplained (a task with a date range, keyed as "Zeitfenster")
- [x] Caption "Ferien, Feiertage, Wochenenden und die schon vergangene Zeit" describes the layers but says nothing about what to do with them — replace with the collision count or drop
- [x] "MIETENDE" toggle is a strong improvement, but it sits above "Wie berechnet?" while its effect shows in the date to the left — add the resulting lease-end date next to the toggle (the month comes from the rule's own derivation step, not from re-deriving it in the card)
- [x] "Als Nächstes" badge and "Kündigungsschreiben bearbeiten" both in blue compete for primary attention within one card
- [x] Gutter date "Do, 3. Sep. 2026" lost its relative line entirely here, while other entries have two — inconsistent (rule-based entries say "berechnete Frist" instead of nothing)

**Mobile**

- [x] Four stacked full-width boxes push the actual content below the fold — collapse Vorhaben/Umzugstag/Ort into one compact row with the date as the only prominent field
- [x] "Vorhaben" is not editable (single option) yet takes the largest box on the smallest screen — render as text
- [x] The sticky "Als ICS exportieren" bar covers content and is the wrong primary action at 0 of 10 done — nobody exports a plan they have not read
- [x] Replace it with nothing, or with "Nächste Aufgabe" scrolling to the first open card
- [x] Timeline is cut off mid-flag by the sticky bar — either hide the timeline on mobile or give it a fixed height above the fold (the bottom bar is gone and the strip is shorter)
- [x] "Alle vorziehen" button sits on its own line and reads as the page's main action — inline it or demote it (inline in the lead paragraph now)
- [x] Progress bar with 0 of 10 filled is pure decoration at this stage; hide until at least one item is checked
- [x] Headline wraps to two lines and consumes a third of the viewport — consider a shorter mobile variant
- [x] Nothing above the fold answers "when do I start" — the first date the user sees is buried in body text (the lead paragraph opens with the next open date as a link into the list)

**Establish the default card state**

- [x] Define the calm baseline card: date in gutter, title, one-line description, source chip — nothing else (card, title, one-line description, source chip. The four tools stay at opacity 0 until hover or focus)
- [x] Make every additional element conditional: warnings, toggles, derivation, and actions only render when they actually apply (audited: 19 conditional elements, 5 unconditional, and those five are the baseline)
- [x] Audit each card variant against the baseline and justify every extra element or delete it (see the two notes above, every extra element sits behind a v-if)

**Remove duplicated information**

- [x] Delete the second collision message below the timeline ("3 Termine auf geschlossenen Tagen") — it repeats the one above (the count moved onto the flag's drag label, where the drag is asking the question)
- [x] Delete the "Bis [date] ist nichts zu tun" line — it restates the next-open date from the intro sentence
- [x] Remove the duplicated progress indicator; keep either the sticky bar or the inline one (both gone, the done fold below the list carries it)
- [x] Remove "Puffer" labels entirely — the spacing already conveys the gap
- [x] Remove the relative time expressions from the gutter ("6 Wochen vorher", "in ca. 7 Wochen"); keep only the absolute date

**Simplify the expired-deadline state**

- [x] Replace the struck-through old date + arrow + new date with a single actionable date in the gutter (the gutter shows the rescue date in red, the expired one moved into the card)
- [x] Move the expired explanation to one short line inside the card, not a full warning block
- [x] Drop "Frist verstrichen" as a heading; the red date already carries that meaning
- [x] Fix the intro sentence so it never names a past date as "die nächste offene" (an expired entry contributes its rescue date, not the day already gone)

**Reduce the timeline chrome**

- [x] Cut the legend to the two toggles (Feiertage, Schulferien) and remove the four static keys
- [x] Remove the "Vergangen" and "Wochenende" legend entries — they are background, not information
- [x] Remove the caption line under the timeline; move the drag hint into a tooltip on first interaction (the hint is a title on the flag itself)
- [x] Reduce weekend shading opacity until it reads as texture, not as content (3.5% tint, 6% hatch)

**Move accounting out of the header area**

- [x] Remove the three-number verification summary; show verification status per card instead (the per-card source chip already carries it, now in neutral grey)
- [x] Keep only one sentence above the timeline: the move date, the task count, and the next open date

**Typography and rhythm**

- [x] Use one type size for all dates in the gutter; no bold/regular mixing within a single entry (fs-sm, weight 400, no mixing)
- [x] Reserve colour for exactly two meanings: overdue (red) and done (green); everything else stays neutral (red for overdue, green for done. The source chip and the next-up badge went neutral)
- [x] Limit each card to one primary action; demote secondary actions to text links

**Verify the result**

- [x] Screenshot a plan where no deadline has passed and no collision exists — it should look almost empty (verified by audit rather than screenshot: the calm card renders 5 elements, all baseline, and the header is one sentence plus the strip)
- [x] Count distinct numbers visible above the first card; target is three or fewer (three: the move date, the task count, the next open date)
- [x] Compare the calm case and the worst case side by side; the difference should be visible at a glance (worst case adds an expired line, a closed-day hint with a button, the Mietende choice and the derivation panel, all behind v-if)
