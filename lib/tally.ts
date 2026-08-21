// The feedback form lives at tally.so/r/ja4XNQ. Only the id is kept here: the
// address you share and the one an embed loads are two different urls.
export const TALLY_FORM_ID = "ja4XNQ";

// Tally's own loader, which sets the iframe's src and keeps its height in step
// with the form. Nothing on the page fetches it until the visitor asks for the
// form, so a visit that never asks reaches tally.so not once.
export const TALLY_WIDGET_URL = "https://tally.so/widgets/embed.js";

// Left aligned, its own title dropped because the page already has one, and it
// keeps its own background: a form at Tally has one palette, while the page has
// two, so a transparent form would be dark text on a dark page for everybody
// reading at night.
export function tallyEmbedUrl(id: string): string {
  const params = new URLSearchParams({
    alignLeft: "1",
    hideTitle: "1",
    dynamicHeight: "1",
  });
  return `https://tally.so/embed/${id}?${params}`;
}
