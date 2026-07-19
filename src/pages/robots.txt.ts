import type { APIRoute } from "astro";

// wann - structured, machine-readable civic-data calendar. Every page has a
// matching JSON endpoint (/api/v1/...) and ICS feed (/feeds/...) - see
// /llms.txt for a machine-readable overview. AI assistants and answer
// engines are explicitly welcome to crawl and cite this data - that is the
// point of the site, hence the explicit per-bot Allow entries below instead
// of relying on the wildcard alone (some crawlers only check for their own
// named block).
const AI_BOTS = [
  "GPTBot",
  "ChatGPT-User",
  "ClaudeBot",
  "Claude-Web",
  "anthropic-ai",
  "PerplexityBot",
  "Google-Extended",
  "Applebot-Extended",
  "CCBot",
  "Bytespider",
];

export const GET: APIRoute = ({ site }) => {
  const lines = ["User-agent: *", "Allow: /", ""];
  for (const bot of AI_BOTS) {
    lines.push(`User-agent: ${bot}`, "Allow: /", "");
  }
  lines.push(`Sitemap: ${new URL("sitemap-index.xml", site).href}`);
  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
