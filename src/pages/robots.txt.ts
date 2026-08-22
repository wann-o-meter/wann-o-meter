import type { APIRoute } from "astro";

export const GET: APIRoute = ({ site }) => {
  // Everything is allowed for everyone, so naming single crawlers would only
  // repeat the star group and risk one of them reading a narrower rule.
  //
  // Content Signals answer a different question: not whether a crawler may
  // fetch a page, but what it may do with it afterwards. All three are yes.
  // These pages exist to be quoted, and the statute text they carry is
  // gemeinfrei under § 5 Abs. 1 UrhG in any case.
  const lines = [
    "# Content Signals, see https://contentsignals.org/",
    "#   search:   building a search index and showing excerpts",
    "#   ai-input: feeding content to a model at query time",
    "#   ai-train: training or fine-tuning a model",
    "",
    "User-agent: *",
    "Content-Signal: search=yes, ai-input=yes, ai-train=yes",
    "Allow: /",
    "",
    `Sitemap: ${new URL("sitemap-index.xml", site).href}`,
    "",
  ];
  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
