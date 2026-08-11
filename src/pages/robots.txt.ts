import type { APIRoute } from "astro";

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
