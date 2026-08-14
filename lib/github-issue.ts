const REPO = "wann-o-meter/wann-o-meter";
const FEEDBACK_EMAIL = "hallo@wannometer.de";

export function newSourceIssueUrl(): string {
  const params = new URLSearchParams({
    title: "Neue Quelle: ",
    body: "URL der Quelle:\n\n(Optional) Mein GitHub-Handle, für die Namensnennung:\n",
    labels: "quelle",
  });
  return `https://github.com/${REPO}/issues/new?${params}`;
}

export function feedbackIssueUrl(): string {
  const params = new URLSearchParams({ title: "Feedback: ", labels: "feedback" });
  return `https://github.com/${REPO}/issues/new?${params}`;
}

// Hand-encoded: mailto wants %20, URLSearchParams would write a literal plus.
export function feedbackMailtoUrl(subject?: string, body?: string): string {
  const query = [
    `subject=${encodeURIComponent(subject ?? "Feedback zu Wann-O-Meter")}`,
    ...(body ? [`body=${encodeURIComponent(body)}`] : []),
  ];
  return `mailto:${FEEDBACK_EMAIL}?${query.join("&")}`;
}
