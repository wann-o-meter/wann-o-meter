import type { APIRoute } from "astro";

export const GET: APIRoute = ({ site }) => {
  // Everything is allowed for everyone, so naming single crawlers would only
  // repeat the star group and risk one of them reading a narrower rule.
  const lines = [
    "User-agent: *",
    "Allow: /",
    "",
    `Sitemap: ${new URL("sitemap-index.xml", site).href}`,
    "",
  ];
  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
