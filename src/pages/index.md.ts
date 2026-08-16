import type { APIRoute } from "astro";
import { allFristSummaries } from "../../lib/frist-api";
import { vorhabenRoutes } from "../../lib/vorhaben-routes";

// The homepage without the page around it. A Cloudflare Worker serves this in
// place of the HTML when a client asks for text/markdown, see README.md.
export const GET: APIRoute = ({ site }) => {
  const url = (path: string) => new URL(path, site).href;
  const plans = vorhabenRoutes().filter((r) => r.path === r.v.slug);

  const body = `# Wann-O-Meter

> Fristen rückwärts vom Termin geplant. Nenne einen Tag, und der Plan sagt, wann
> du anfangen musst. Jede Frist nennt den Paragrafen dahinter.

## Pläne

Ein Datum eingeben, und jede Frist wird davon zurückgerechnet, mit den
Feiertagen des gewählten Bundeslands.

${plans.map((r) => `- [${r.v.label}](${url(`/${r.path}/`)}): ${r.description}`).join("\n")}

## Fristen

Eine Seite je Frist, mit dem Wortlaut des Gesetzes.

${allFristSummaries().map((f) => `- [${f.label}](${url(f.url)}): ${f.source.label ?? "keine gesetzliche Frist"}`).join("\n")}

## Für Maschinen

- Fristen als JSON: ${url("/api/v1/fristen.json")}
- OpenAPI: ${url("/openapi.json")}
- API-Katalog nach RFC 9727: ${url("/.well-known/api-catalog")}
- Überblick als Text: ${url("/llms.txt")}

Angaben ohne Gewähr, keine Rechtsberatung.
`;

  return new Response(body, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
