export interface TaskCta {
  kind: "letter" | "link";
  label: string;
  url?: string;
}

const LINK_CTAS: Record<string, TaskCta> = {
  nachsendeauftrag: {
    kind: "link",
    label: "Nachsendeauftrag bei der Post",
    url: "https://shop.deutschepost.de/nachsendeservice-beauftragen",
  },
  "kfz-ummeldung": {
    kind: "link",
    label: "i-Kfz beim Kraftfahrt-Bundesamt",
    url: "https://www.kba.de/DE/Themen/ZentraleRegister/Digitale_Fahrzeugzulassung/iKfz/ikfz_node.html",
  },
};

const LETTER_CTAS: Record<string, string> = {
  "wohnung-kuendigen": "Kündigung der Wohnung",
  "internetanbieter-kuendigen-ummelden": "Kündigung beim Internetanbieter",
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
