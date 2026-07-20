// GitHub is the site's only contribution queue (see CONTRIBUTING.md) - every
// "suggest a source" / "report a wrong source" UI affordance builds a
// prefilled issues/new link instead of its own form or backend.
const REPO = "wann-o-meter/wann-o-meter";

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
