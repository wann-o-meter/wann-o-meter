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

export function feedbackMailtoUrl(): string {
  return `mailto:${FEEDBACK_EMAIL}?subject=${encodeURIComponent("Feedback zu Wann-O-Meter")}`;
}
