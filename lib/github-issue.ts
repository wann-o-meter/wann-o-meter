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

export function feedbackMailtoUrl(subject?: string, body?: string): string {
  const params = new URLSearchParams({
    subject: subject ?? "Feedback zu Wann-O-Meter",
  });
  if (body) params.set("body", body);
  return `mailto:${FEEDBACK_EMAIL}?${params}`;
}
