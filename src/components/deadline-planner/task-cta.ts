export interface TaskCta {
  kind: "letter" | "link";
  label: string;
  url?: string;
}

// Labels never restate the card title, the card already says what this is.
const LINK_CTAS: Record<string, TaskCta> = {
  nachsendeauftrag: {
    kind: "link",
    label: "Bei der Post beauftragen",
    url: "https://shop.deutschepost.de/nachsendeservice-beauftragen",
  },
  "kfz-ummeldung": {
    kind: "link",
    label: "Online ummelden (i-Kfz)",
    url: "https://www.kba.de/DE/Themen/ZentraleRegister/Digitale_Fahrzeugzulassung/iKfz/ikfz_node.html",
  },
};

const LETTER_CTAS: Record<string, string> = {
  "wohnung-kuendigen": "Kündigung",
  "internetanbieter-kuendigen-ummelden": "Kündigung",
};

export function taskCtaFor(id: string): TaskCta | null {
  if (id in LINK_CTAS) return LINK_CTAS[id];
  if (id in LETTER_CTAS) return { kind: "letter", label: LETTER_CTAS[id] };
  return null;
}

export const LETTER_TEMPLATE = `[Ihr Name]
[Ihre Straße, Hausnummer]
[PLZ, Ort]

[Name des Anbieters]
[Straße, Hausnummer]
[PLZ, Ort]

[Ort], [Datum]

Betreff: Kündigung des Vertrags [Vertragsbezeichnung], Kundennummer [Kundennummer]

Sehr geehrte Damen und Herren,

hiermit kündige ich den oben genannten Vertrag zum nächstmöglichen Termin, hilfsweise fristgerecht zum [Kündigungsfrist gemäß Vertrag].

Bitte bestätigen Sie mir den Erhalt dieser Kündigung sowie das Vertragsende schriftlich.

Mit freundlichen Grüßen
[Ihr Name]`;
