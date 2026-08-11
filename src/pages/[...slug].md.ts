import type { APIRoute } from "astro";
import { appliesTo } from "../../lib/facets";
import { byOffset, offsetLabel, sourceLabel } from "../../lib/offset-label";
import { vorhabenRoutes } from "../../lib/vorhaben-routes";

export function getStaticPaths() {
  return vorhabenRoutes().map((r) => ({ params: { slug: r.path }, props: r }));
}

export const GET: APIRoute = ({ props, site }) => {
  const { v, variant, title, description, path } = props as ReturnType<typeof vorhabenRoutes>[number] & {
    path: string;
  };
  const canonical = new URL(`/${path}/`, site).href;

  const lines = variant.deadlines
    .filter((d) => appliesTo(d, []))
    .sort(byOffset)
    .map((d) => {
      const source = d.source_url ? `[${sourceLabel(d)}](${d.source_url})` : sourceLabel(d);
      const note = d.note ? `\n  ${d.note}` : "";
      return `- **${offsetLabel(d, v.anchorLabel)}**: ${d.label} (${source})${note}`;
    });

  const body = `# ${title}

> ${description}

Alle Fristen sind relativ zum ${v.anchorLabel} angegeben. Quelle: ${canonical}

## Fristen

${lines.join("\n")}

## Hinweise

- "Erfahrungswert" heißt: die Frist ist noch nicht gegen ihre Rechtsgrundlage geprüft. Nicht als belastbare Frist zitieren.
- Angaben ohne Gewähr, keine Rechtsberatung.
`;

  return new Response(body, {
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
  });
};
