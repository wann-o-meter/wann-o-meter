import type { APIRoute } from "astro";
import { appliesTo } from "../../../lib/facets";
import { byOffset, offsetLabel } from "../../../lib/offset-label";
import { BUNDESWEIT_SLUG, loadAllVorhaben } from "../../../lib/vorhaben-data";
import type { VorhabenData } from "../../../lib/vorhaben-data";

// The same Fristen as one image, for a CMS that strips iframes and scripts.
// ponytail: text drawn as SVG, no screenshot pipeline. If a partner ever needs
// a raster the browser can convert this one.
export function getStaticPaths() {
  return loadAllVorhaben().map((v) => ({ params: { vorhaben: v.slug }, props: { v } }));
}

const WIDTH = 640;
const ROW = 30;
const PAD = 20;
// Title, source line and the air below them.
const HEAD = 72;

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export const GET: APIRoute = ({ props }) => {
  const { v } = props as { v: VorhabenData };
  const variant = v.variants.find((x) => x.slug === BUNDESWEIT_SLUG) ?? v.variants[0];
  const entries = variant.deadlines.filter((d) => appliesTo(d, [])).sort(byOffset);
  const height = PAD + HEAD + entries.length * ROW;

  const rows = entries
    .map((d, i) => {
      const y = HEAD + i * ROW;
      return [
        `<text x="${PAD}" y="${y}" font-size="13" fill="#4d545e" font-family="monospace">${escapeXml(
          offsetLabel(d, v.anchorLabel),
        )}</text>`,
        `<text x="${PAD + 170}" y="${y}" font-size="13" fill="#14161a">${escapeXml(d.label)}</text>`,
      ].join("");
    })
    .join("");

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${height}" viewBox="0 0 ${WIDTH} ${height}" font-family="system-ui, sans-serif" role="img" aria-label="${escapeXml(
    `${v.label}: ${entries.length} Fristen`,
  )}"><rect width="${WIDTH}" height="${height}" fill="#ffffff"/><text x="${PAD}" y="${
    PAD + 18
  }" font-size="17" font-weight="600" fill="#14161a">${escapeXml(
    `${v.label}: ${entries.length} Fristen`,
  )}</text><text x="${PAD}" y="${
    PAD + 38
  }" font-size="12" fill="#4d545e">wannometer.de</text>${rows}</svg>`;

  return new Response(svg, {
    headers: { "Content-Type": "image/svg+xml; charset=utf-8" },
  });
};
