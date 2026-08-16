import type { APIRoute } from "astro";
import { allFristSummaries } from "../../../lib/frist-api";

// RFC 9727: one place an agent can look to find every API this site has,
// without crawling for it. The linkset points at the machine-readable
// description, the human-readable docs, and the data itself.
//
// GitHub Pages decides Content-Type from the file extension and this resource
// deliberately has none, so it leaves here as application/octet-stream. The
// Cloudflare rule in README.md overrides it to application/linkset+json.
export const GET: APIRoute = ({ site }) => {
  const url = (path: string) => new URL(path, site).href;
  const count = allFristSummaries().length;

  const linkset = {
    linkset: [
      {
        anchor: url("/api/v1/fristen.json"),
        "service-desc": [
          { href: url("/openapi.json"), type: "application/json" },
        ],
        "service-doc": [{ href: url("/api/"), type: "text/html" }],
        "service-meta": [{ href: url("/llms.txt"), type: "text/plain" }],
        title: `Fristen API: ${count} German statutory deadlines with the Paragraf behind each one`,
      },
    ],
  };

  return new Response(JSON.stringify(linkset, null, 2), {
    headers: {
      "Content-Type":
        'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
      "Access-Control-Allow-Origin": "*",
    },
  });
};
