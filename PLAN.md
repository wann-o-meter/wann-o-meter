# Projekt-Brief: „Wann-Plattform" (Arbeitstitel, Domain offen)

> Autoritatives Kontext-Dokument für Claude Code Sessions.
> Bei Zielkonflikten in einer Session gilt: **dieses Dokument schlägt spontane
> Erweiterungsideen.** Wenn eine Anweisung des Nutzers diesem Dokument
> widerspricht, den Widerspruch benennen, dann der Anweisung folgen.

---

## 1. Produktvision

Eine Plattform, die die Frage **„Wann ist der beste Zeitpunkt für X?"** mit
geprüften, quellenbelegten Daten beantwortet statt mit generiertem Text.

**Das Produkt in einem Satz:** Ein Kalender, auf den man geprüfte
Zeitschichten legt (Feiertage, Ferien, Saisonen, Klimamuster, Events), jede
Kombination teilbar als URL und abonnierbar als Kalender-Feed — kuratierte
Presets beantworten die Fragen, die Nutzer nicht selbst zusammenklicken
wollen.

**Kernmechanik:** fragmentierte öffentliche Quellen (PDFs, Behördenseiten,
Verbandskalender, amtliche Daten) → LLM-Extraktion oder Berechnung →
strukturierte Zeitfenster → Ebenen-Kalender + statische Seiten + JSON-API +
ICS-Feeds.

**Wow-Moment:** Nutzer togglet drei Ebenen, sieht sofort das passende
Zeitfenster und nimmt es mit einem Klick als Kalender-Abo mit.

## 2. Die Verfassungsregel (bei JEDEM Feature prüfen)

> **Jede Seite und jede Ebene ist eine Datenantwort, kein Artikel.**
> Test: *Steht hier ein Datum oder Zeitraum, das sich (mindestens) jährlich
> ändert und das man als Kalender abonnieren kann?*
> - JA → gehört auf die Plattform.
> - NEIN (zeitlose Antwort wie „morgens ist Brot frischer") → wird NICHT gebaut.

Zweiter Test für Grenzfälle (der Zerlegungs-Test): Fragen wie „Wann
heiraten?" sind als Ganzes subjektiv und damit out of scope — aber sie
zerlegen sich in faktische Teilfragen (feiertagsnahe Samstage, historisch
warme Monate, eventfreie Wochenenden), die JEWEILS als Ebene in scope sind.
Regel: **Reduziert sich eine Frage auf verifizierbare Kalender-/Klima-/
Saisonfakten, ist sie (als Preset) in scope. Erfordert die Antwort das
Abwägen persönlicher Präferenzen, trifft die Plattform NIE die Entscheidung —
sie zeigt nur die Fakten-Ebenen und lässt den Menschen wählen.**

## 3. Was das Produkt bewusst NICHT ist

- **Kein Freitext-Suchfeld als Antwort-Maschine.** Kein generatives „für
  alles eine Antwort" — das würde Abdeckung versprechen, die die Daten nicht
  haben, oder Laufzeit-LLM-Halluzination erzwingen. Suche existiert nur als
  Typeahead über VORHANDENE Subjekte/Ebenen/Presets. Leere Treffer zeigen
  nächstliegende Ebenen + werden geloggt (Priorisierungs-Backlog).
- **Kein Rechts-Kompendium** („Darf ich...?") — RDG-Nähe, Einzelfall-Territorium.
  Nur „Wann", nie „Darf".
- **Keine Echtzeit-Daten** (keine Live-Preise, keine tagesaktuellen Ausfälle,
  keine Wettervorhersage). Nur Muster, Saisonen, geplante/beschlossene
  Termine. Klimatologie ja, Wetterbericht nein.
- **Kein Preis-Scraping** (fremde Preisdatenbanken = §87a-Territorium +
  Echtzeit-Betriebslast). Preis-MUSTER aus amtlichen/offenen Quellen erlaubt
  (Vertikale „Preismuster").
- **Keine Besucherfrequenz-/Auslastungsdaten aus proprietären Quellen.**
  „Wann ist es im Supermarkt am leersten" klingt wie eine Wann-Frage, aber
  die einzigen Quellen (Google Popular Times, App-Bewegungsdaten) sind
  fremde geschützte Datenbanken. Wird NICHT gebaut. Abgrenzung:
  VERÖFFENTLICHTE Zeiten (Öffnungszeiten, Saisonstart, Frühschwimmer-Slot)
  = Fakten, ok. GEMESSENE Auslastung = tabu. SELBST ABGELEITETER Druck aus
  eigenen Daten (Ferienüberlappung, Eventdichte) = ok, eigene Rechenleistung.
- **Keine LLM-generierten Fließtext-Artikel** als Hauptinhalt. LLM dient der
  EXTRAKTION, nicht der Content-Generierung.
- **Keine Regel-Engine in YAML.** Berechnungsregeln (Ostern, Brückentage)
  sind Code in /lib, nie deklarative Syntax in Datendateien.
- **Kein Login, kein Sync, kein Nutzer-Account, keine Nutzer-Presets in V1.**
- **Kein Request-Metering/API-Kontingente.** Monetarisierung läuft über
  Lizenz + Zusicherungen, nicht über Zähler (Abschnitt 9).

## 4. UI-Konzept: Der Ebenen-Kalender

### 4.1 Grundmodell
Eine Kalenderansicht (Monats-/Jahresübersicht), auf die **Ebenen** (Layer)
getoggelt werden. Jede Ebene = ein materialisiertes Zeitfenster-Set aus dem
Datenmodell (z. B. „Feiertage BW", „Apfelsaison", „Sommerferien 2027",
„historisch 20–30 °C in Region X"). Ebenen sind farbcodiert, Quellen-Badge
pro Ebene („Quelle: KMK, Stand 03/2026").

### 4.2 Zwei Modi
1. **Overlay-Modus (V1):** Ebenen werden übereinander im Kalender
   angezeigt. Der Mensch schaut und wählt selbst. Reines Rendern.
2. **Fenster-Modus (nach V1):** Die Maschine schneidet Mengen:
   „Zeiträume, die Ebene A UND B erfüllen UND NICHT C" (Negativ-Filter =
   Mengensubtraktion). Implementiert als Intervall-Schnittmengen-Engine in
   /lib — pur funktional, testbar. Hinweis: Das ist derselbe Algorithmus
   wie der spätere Brückentage-Kollisionsindex. Einmal bauen.

### 4.3 URL als Zustand (strategisch wichtig)
Der komplette Filterzustand (aktive Ebenen, Region, Jahr, Modus)
serialisiert in URL-Parameter. Konsequenzen:
- **Presets = gespeicherte URLs**, kuratiert als YAML (/data/presets/*.yaml),
  jedes Preset wird als eigene STATISCHE Landingpage gerendert
  (z. B. „Wann heiraten 2027 in BW?" → Seite mit vorgewähltem Ebenen-Set +
  erklärendem Kurztext). Presets sind die SEO-Antwort auf Fragen, die kein
  Suchfeld beantworten soll.
- **Teilen** = Link kopieren.
- **Premium-Feed (später) = abonnierter Filterzustand**: „diese URL als
  ICS abonnieren" ist das Bezahlprodukt. Die Monetarisierung fällt aus der
  UI heraus, statt daneben gebaut zu werden.

### 4.4 Die Kalender-Komponente ist die EINE Vue-Insel
Ebenen-Toggles + Monatsnavigation = echter UI-Zustand → hierfür (und nur
hierfür) wird Vue nachgerüstet (`npx astro add vue`). Alles andere bleibt
statisches Astro. Die statischen Subjekt-Seiten bleiben daneben bestehen:
Sie sind die SEO-Türen, der Kalender ist die App.

### 4.5 V1-Zäune für den Kalender
- **Drei Ebenen in V1** (die billigsten): (1) Feiertage (Library-berechnet,
  alle Bundesländer), (2) Schulferien (amtliche KMK-/Länder-PDFs),
  (3) EINE Fleiß-Ebene nach Wahl des Betreibers: Gemüsesaison ODER
  Klimatologie-Bins. Nicht mehr.
- **Regionsgranularität: Bundesland.** Keine Städte/Landkreise in V1
  (Datenmenge im Client klein halten).
- **Klimatologie** (falls gewählt) = vorberechnete historische Wochen-Bins
  pro Region als statische Daten (DWD/Open-Meteo-Archiv). NIE ein
  Wetter-API-Call zur Laufzeit.
- **Keine Nutzer-Presets.** Presets kuratiert der Betreiber per Hand als YAML.

## 5. Datenmodell (generischer Kern — kategorieunabhängig ab Zeile 1)

### 5.1 Grundprinzip: Definition vs. Materialisierung

Zeitfenster ENTSTEHEN auf drei Wegen (Definitionsschicht):
1. **Handgepflegte Daten** — YAML in /data (z. B. Apfelsaison).
2. **Pipeline-Daten** — YAML in /data, vom Scraper/LLM als PR vorgeschlagen
   (z. B. Schulferien, Freibad-Termine). Merke: Schulferien SEHEN
   berechenbar aus, sind aber BESCHLOSSEN (KMK, 5 Jahre voraus) → Daten.
3. **Berechnungsregeln** — Code in /lib (bewegliche Feiertage via
   etablierter Library, z. B. `date-holidays` oder `feiertagejs`, mit
   Bundesland-Logik; Brückentage-Fenster als eigene Ableitung darauf).

Leitfrage pro Quelle: **„Dekretiert oder deriviert?"**
Dekretiert (beschlossen, veröffentlicht) → Daten. Deriviert (aus Regel
ableitbar) → Code.

Zur Build-Zeit werden alle drei Wege zu EINEM Format **materialisiert**:
konkrete Zeitfenster pro Jahr, rollierendes Fenster (aktuelles Jahr + 2).
Wiederkehrende Saisonen (jahr: null) → Jahres-Instanzen; Regeln →
ausgerechnet; fixe Termine → durchgereicht.
**Kalender-UI, Seiten, JSON, ICS und (späteres) SQLite-Artefakt konsumieren
AUSSCHLIESSLICH die materialisierte Schicht.** Herkunft steht nur in der
Provenienz, ändert nie das Format.

### 5.2 Zeitliche Auflösung: ISO-8601-Teilangaben + Präzisions-Flag

EIN von/bis-Feld als ISO-8601-String reduzierter Genauigkeit — die
Stringlänge IST die Auflösung:
- `"--08"` = Monat ohne Jahr (wiederkehrend, monatsgrob)
- `"2027-07-29"` = taggenau
- `"2026-05-01T06:30"` = minutengenau (NUR für veröffentlichte Zeiten,
  siehe Abschnitt 3)

Parser in /lib: Stringlänge → Auflösung (monat|tag|minute).
Getrennt davon: `praezision: exakt|zirka` (Schulferien = taggenau UND
exakt; Klimatologie = ggf. taggenau notiert, aber inhärent zirka).
Ausgabeverhalten: ICS macht aus Tag-Auflösung Ganztages-Events;
Monats-/Zirka-Fenster werden als Saisonbalken gerendert und sind per
`ics: true|false` pro Fenster aus Feeds ausschließbar.

### 5.3 YAML-Format (Source of Truth: /data/{kategorie}/{subjekt}.yaml)

```yaml
subjekt:
  slug: apfel
  name: Apfel
  kategorie: saisonkalender
  region: DE            # nullable; DE-BW etc. möglich (V1: max. Bundesland)
  metadaten: {}         # kategoriespezifisch, frei

zeitfenster:
  - typ: hauptsaison    # kategoriespezifisches Vokabular
    jahr: null          # null = jährlich wiederkehrend; sonst konkretes Jahr
    von: "--08"
    bis: "--11"
    praezision: zirka
    ics: false
  - typ: lagerware
    jahr: null
    von: "--12"
    bis: "--04"         # Jahreswechsel-Überlauf: bis < von ist ERLAUBT
    praezision: zirka
    ics: false

quellen:                # PFLICHT — kein Zeitfenster ohne Quelle
  - url: https://...
    lizenz: tos_geprueft   # amtlich_par5|dl_de_by|cc_by|tos_geprueft|
                           # angefragt_ok|eigene_ableitung
    lizenz_hinweis: null   # Attributionstext falls nötig
    abgerufen_am: 2026-07-11
    extraktion: llm        # manuell|llm|parser
    konfidenz: 0.9         # nur bei llm
```

**Ein Zod-Schema in /lib definiert Typen UND Validierung aus einer Quelle;
der Build lehnt invalide Dateien ab. KEINE TypeScript-Datei pro Kategorie —
Daten sind Daten, nicht Code.**

Presets (/data/presets/*.yaml): slug, name, beschreibung (2–3 Sätze,
faktisch), ebenen[] (Referenzen auf Kategorie/Subjekt/Filter), region,
modus. Werden zu statischen Landingpages + vorbelegten Kalender-URLs.

### 5.4 Speicher-Entscheidung

- **Source of Truth: YAML im Repo.** Git-Diff = Review = Freigabe.
  NIEMALS SQLite/DB als eingecheckte Datenquelle (Binärblob: kein Diff,
  kein Review, keine Blame-Historie).
- **Optional ab Bedarf: SQLite als Build-Artefakt** (nicht committet,
  wegwerfbar, reproduzierbar), wenn Build-Steps erstmals über Kategorien
  joinen/rechnen müssen. Für V1 reicht glob + Zod + Array-Filter
  (Astro Content Collections). Später-Bonus: dieselbe Datei als
  öffentlicher Download („komplette DB als SQLite").

## 6. Lizenz-Systematik (bei JEDER neuen Quelle anwenden)

Grundsatz: Fakten sind nicht schutzfähig — Darstellungen und ganze
Datenbanken schon.

1. **Amtliche Werke (§5 UrhG):** Gesetze, Verordnungen, amtliche
   Bekanntmachungen → frei (Ferien-PDFs, Feiertagsgesetze).
2. **Datenlizenz Deutschland / CC-BY:** GovData, DWD, destatis → frei mit
   Namensnennung. Attribution ins quellen-Feld, wird auf der Seite gezeigt.
3. **Private Quellen (APIs, CSVs, Verbandskalender):** ToS lesen; unklar →
   freundliche Anfrage-Mail (Vorlage im Repo). Bis zur Klärung: nicht nutzen.
4. **Rote Linie (§87a UrhG):** NIE eine einzelne fremde kuratierte
   Datenbank im Wesentlichen übernehmen (kompletter Datensatz EINES
   Anbieters, Preishistorien von idealo/Keepa, Google Popular Times).
   Viele fragmentierte Quellen aggregieren = das Geschäftsmodell;
   eine Quelle klonen = verboten.
5. Darstellungen (Layouts, Grafiken, Texte) nie kopieren — nur Fakten
   extrahieren, eigene Darstellung bauen.

## 7. Architektur

Grundsatz: Auslieferung ist statisch, Dynamik ist die Ausnahme. Zero-Ops.

- **Frontend:** Astro (SSG), Zero-JS-Default, reine .astro-Templates für
  alle Seiten. Vue NUR für die Kalender-Komponente (Abschnitt 4.4).
- **Suche:** Pagefind (statisch) + Typeahead über bekannte Subjekte/Presets.
  Erst ab >50 Seiten relevant.
- **Daten im Repo:** /data/{kategorie}/*.yaml + /data/presets/*.yaml.
  Build validiert gegen Zod-Schema aus /lib.
- **Materialisierungs-Step (Build):** YAML + /lib-Berechnungen → konkrete
  Zeitfenster (aktuelles Jahr + 2). Alle Ausgaben speisen sich NUR hieraus.
- **Generierung pro Build:** HTML-Seiten (Kategorie-Übersichten,
  Subjekt-Seiten, Preset-Landingpages, Kalender-App-Seite),
  /api/v1/{kategorie}/{subjekt}.json, /feeds/{kategorie}/{subjekt}.ics.
  Die URL-Struktur ist der Vertrag — Unterbau später austauschbar.
- **/lib (plattformneutrales TypeScript, Vitest-getestet):** Zod-Schema,
  ISO-Teilangaben-Parser, Materialisierung, Feiertags-/Brückentage-
  Berechnung, ICS-Generator, Intervall-Schnittmengen-Engine (Fenster-Modus,
  nach V1). Keine Deno-/Astro-Abhängigkeiten in /lib.
- **/pipeline (Python, lokal oder GitHub Action, KEINE Laufzeit-Abhängigkeit
  der Site):** Fetch → Extraktion → YAML auf Branch → **Pull Request =
  Freigabe-Queue** → menschlicher Diff-Review → Merge triggert Build.
  Die Pipeline schreibt ausschließlich YAML im Schema 5.3 — nie Code, nie SQL.
  **Extraktions-Strategie pro Quelle (nicht pro Pipeline-Philosophie), Faustregel
  Homogenität × Volumen:**
  1. *Parser* (`extraktion: parser`, kein Modell zur Laufzeit): ein Format,
     viele Datensätze — CSV/JSON-API/Directory-Listing mit dokumentiertem
     Schema (z. B. DWD Klimadaten). LLM darf den Parser einmalig SCHREIBEN
     (Claude Code), das Ergebnis ist eingecheckter, getesteter Code. Bei
     einmaligen Bulk-Quellen (Klimatologie-Historie) läuft das Skript
     einmalig, nicht als Cron.
  2. *LLM pro Abruf* (`extraktion: llm`, Konfidenz-Feld pflegen): viele
     Formate, wenige Datensätze pro Quelle — Ferien-PDFs, Freibad-Fließtext,
     jede Kommune anders. Bei jährlichem Rhythmus sind die Modellkosten
     irrelevant; verfrühte Parser-Optimierung ist hier die Falle.
  3. *Generierter Scraper mit LLM-Fallback*: ein Portal, viele gleichförmige
     Seiten (z. B. 50 Freibäder im selben Kommunal-Template). Läuft
     deterministisch; wenn die Zod-Validierung oder Plausibilitätschecks
     (Datum im erwarteten Bereich? Region im Enum?) reißen, Fallback auf
     Strategie 2 statt still zu scheitern.

  V1-Quellen einsortiert: Feiertage = gar keine Pipeline (Library in /lib,
  `extraktion: parser`). Schulferien-PDFs + Gemüsesaison-Verbandsseiten =
  Strategie 2. DWD-Klimatologie (falls/wenn gebaut, siehe Abschnitt 10 Punkt 2)
  = Strategie 1, einmalig.
- **Hosting:** Cloudflare Pages (Header-Kontrolle: CORS auf /api/, korrekte
  Content-Types für .ics; Free-Tier praktisch ohne Bandbreitengrenze).
  GitHub Pages nur als Notlösung.
- **Kein Backend in V1.** Supabase/Edge Functions erst mit Premium-Feeds.

## 8. V1-Scope & Definition of Done

**V1 = der Ebenen-Kalender mit drei Ebenen + statische Seiten + Feeds.**
Ziel: in wenigen Wochenenden VERÖFFENTLICHT. Erst wenn V1 live ist und
benutzt wird, kommt Ebene vier.

Umfang:
1. Drei Ebenen (Abschnitt 4.5): Feiertage (berechnet), Schulferien
   (Pipeline/amtlich), eine Fleiß-Ebene (Betreiber wählt: Gemüsesaison
   oder Klimatologie-Bins).
2. Kalender-App (Overlay-Modus, Bundesland-Auswahl, Ebenen-Toggles,
   URL-Zustand, ICS-Knopf pro Ebene).
3. Statische Subjekt-Seiten + Kategorie-Übersichten (Saisonbalken bzw.
   Termine je nach Auflösung, „Quelle & Stand"-Badge, ICS + JSON-Link).
4. 2–3 handkuratierte Presets als Landingpages.
5. /api/v1/ (JSON) + /feeds/ (ICS), Sitemap, Meta-Tags, saubere URLs.
6. Footer: Free-Versprechen + Nutzungsbedingungen-Satz + Impressum.

**Definition of Done:**
- [ ] Unter einer Domain veröffentlicht
- [ ] Betreiber hat mindestens einen ICS-Feed selbst abonniert; Termine
      erscheinen korrekt im Kalender
- [ ] Ein Außenstehender hat es benutzt
- [ ] Hält beliebige Lastspitzen aus (bei statischem Hosting automatisch)

## 9. Monetarisierung (gestaffelt — NICHTS davon in V1 bauen)

Grundsatz (im Footer ab Tag 1 kommuniziert): Basisdaten und Einzel-Feeds
sind kostenlos und bleiben es. **Monetarisiert werden Zusicherungen und
Bequemlichkeit, nicht Zugriffe. KEIN Request-Metering, keine Kontingente** —
die Auslieferung ist statisch und kostet nichts; Zähler davor würden
Zero-Ops opfern, die Falschen treffen (Caching-Kunden zahlen viel, nutzen
wenig Requests) und den freien Marketing-Kanal abwürgen.

1. **Frei (immer):** alle Seiten, Kalender, Einzel-ICS-Feeds, JSON für
   private/nicht-kommerzielle Nutzung. Anonym, ungezählt.
2. **Premium (~2 €/Monat, nach V1):** personalisierter Kombi-Feed =
   abonnierter Filterzustand des Kalenders (Abschnitt 4.3).
   Architektur liegt vor: Stripe Payment Link → Webhook →
   subscribers-Tabelle → Capability-URL /feed/{token}.ics → Edge Function
   mit geteilter /lib-ICS-Generierung.
3. **Kommerzielle Daten-Lizenz (B2B, bei realer Nachfrage):** verkauft wird
   (a) die Lizenz zur kommerziellen Nutzung (ToS-Satz ab Tag 1: „privat
   frei, kommerziell nur mit Vereinbarung"), (b) Stabilitäts-/Frische-
   Zusagen (versionierte Endpoints, Deprecation-Fristen, „Daten ≤ X Tage
   nach amtlicher Veröffentlichung"), (c) Bequemlichkeit: Bulk-Download
   (das SQLite-Artefakt als Produktfeature) + Changed-Feed/Webhook.
   Flat pro Tier (Indie/Firma/Redistribution), via Capability-URL
   /api/commercial/{token}/... über dünne Edge Function. Freie Pfade
   bleiben statisch und unangetastet.
4. **Affiliate (selektiv):** nur wo die Antwort eine Kaufhandlung auslöst
   (Reise-Timing, Saison-Equipment). Gekennzeichnet, sparsam.

## 10. Ausbau-Vertikalen (NACH V1; Reihenfolge = Vorschlag)

1. **Fenster-Modus** (Intervall-Schnittmengen + Negativ-Filter) — und damit
   automatisch der **Brückentage-Kollisionsindex** („überlaufene vs.
   unterschätzte Brückentage", derselbe Algorithmus).
2. **Urlaubs-Timing komplett:** Klimatologie pro Ziel/Woche (DWD/
   Open-Meteo-Archiv, einmalig), Quellmarkt-Inversion (Ferienkalender
   von 15–20 europäischen Quellmärkten → „wer hat frei, wenn ich nach X
   will" — die große Fleißarbeits-Wette).
3. **Kommunale Saisonen:** Freibad-Saison, Grünschnitt-Termine,
   verkaufsoffene Sonntage (LLM-Scraping auf Kommunal-Websites).
4. **Event-/Messe-Preisdruck:** wann Städte voll/teuer sind. Jährlich träge.
5. **Preismuster** („Wann kaufen?"): Saisonzyklen aus amtlichen Indizes
   (destatis) + Klimadaten — NICHT aus gescrapten Shop-Preisen.
   Langfrist-Option: Zeitreihenmodellierung/Anomalieerkennung (Betreiber
   hat Thesis-Expertise) — „aktueller Klimageräte-Peak ist
   Hitzewellen-Anomalie, kein neues Preisniveau".
6. **MCP-Server:** dieselben Daten als Agenten-Tools (optimale_fenster,
   saison_status, ...), sobald /api/v1 stabil.
7. **BT-Integration:** Urlaubsfenster-Ebenen im Büro-Toolbox-Urlaubsplaner
   (persönliche Constraints × öffentliche Datenschichten).
8. **Kita-Schließtage (schlafend):** komplettes Konzept existiert als
   separater Brief. Aktivieren erst bei eigener Betroffenheit des
   Betreibers — bis dahin nicht anfassen.

## 11. Erste Claude Code Session — Aufgabenliste (Reihenfolge einhalten)

1. Repo-Setup: Astro + TypeScript, /lib mit Vitest, /data, /pipeline
   (Python), Cloudflare-Pages-Deploy via GitHub Action.
2. /lib: Zod-Schema (YAML-Format 5.3) + ISO-Teilangaben-Parser
   (Stringlänge → monat|tag|minute, Jahreswechsel-Überlauf bis < von)
   — mit Tests.
3. /lib: Materialisierung (5.1, rollierend Jahr + 2) + Feiertags-Library
   andocken (alle Bundesländer) + Brückentage-Ableitung — mit Tests.
4. /lib: ICS-Generator + Zeitfenster-Helfer („aktuelles Fenster?",
   „nächstes ab Datum") auf der materialisierten Schicht — mit Tests.
5. Seed-Daten: Schulferien aller Bundesländer für 2 Schuljahre als YAML
   (aus amtlichen Quellen, quellen-Block ausfüllen!) + die gewählte
   Fleiß-Ebene mit 5–10 Subjekten.
6. Statische Seiten: Kategorie-Übersichten + Subjekt-Detailseiten
   (Saisonbalken/Termine je nach Auflösung, Quelle-&-Stand-Badge,
   ICS-Knopf, JSON-Link).
7. Kalender-App: Vue nachrüsten (`npx astro add vue`), Overlay-Modus,
   Bundesland-Auswahl, Ebenen-Toggles, URL-Zustand, ICS pro Ebene.
8. Build-Ausgabe: /api/v1/*.json + /feeds/*.ics + Sitemap.
9. 2–3 Presets als YAML + Landingpages.
10. /pipeline: erstes Extraktions-Skript (Ferien-PDF → LLM → YAML auf
    Branch → PR).
11. Footer: Free-Versprechen, Nutzungsbedingungen-Satz, Impressum-Platzhalter.

**Explizit NICHT in Session 1 (auch nicht „nur schnell"):**
vierte Ebene, Fenster-Modus, Städte-Granularität, Supabase, Premium-Feeds,
Stripe, MCP, Suche/Pagefind, SQLite-Artefakt, Nutzer-Presets, Admin-UI,
Regel-Engine in YAML, Besucherfrequenz-Anything, Kita-Anything.
