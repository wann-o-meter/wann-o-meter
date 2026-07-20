// GitHub is the site's only contribution queue (see CONTRIBUTING.md) - every
// "suggest a source" / "report a wrong source" / "give feedback" UI
// affordance builds a prefilled issues/new link instead of its own form or
// backend.
const REPO = "wann-o-meter/wann-o-meter";
// Same address already published in Impressum/Datenschutz - the mail-based
// feedback path reuses it rather than adding a second contact address.
const FEEDBACK_EMAIL = "hallo@wannometer.de";

export function newSourceIssueUrl(): string {
  const params = new URLSearchParams({
    title: "Neue Quelle: ",
    body: "URL der Quelle:\n\n(Optional) Mein GitHub-Handle, für die Namensnennung:\n",
    labels: "quelle",
  });
  return `https://github.com/${REPO}/issues/new?${params}`;
}

export function reportSourceIssueUrl(pageTitle: string, pageUrl: string, sourceUrl: string): string {
  const params = new URLSearchParams({
    title: `Fehlerhafte Quelle: ${pageTitle}`,
    body: `Seite: ${pageUrl}\nQuelle: ${sourceUrl}\n\nWas stimmt nicht?\n`,
    labels: "quelle-fehler",
  });
  return `https://github.com/${REPO}/issues/new?${params}`;
}

// General site feedback (bugs, UX, ideas - anything that isn't about one
// specific source, see reportSourceIssueUrl above for that) via either
// channel; GitHub for anyone happy to file an issue, mail for anyone who
// isn't.
export function feedbackIssueUrl(): string {
  const params = new URLSearchParams({ title: "Feedback: ", labels: "feedback" });
  return `https://github.com/${REPO}/issues/new?${params}`;
}

export function feedbackMailtoUrl(): string {
  return `mailto:${FEEDBACK_EMAIL}?subject=${encodeURIComponent("Feedback zu Wann-O-Meter")}`;
}
