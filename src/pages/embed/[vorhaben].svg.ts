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

const ROW = 30;
const PAD = 20;
// Title, source line and the air below them.
const HEAD = 72;
const SIZE = 13;
// No text metrics without a browser, so measure by character: monospace is
// exactly 0.6em per glyph, the sans column gets the widest plausible average.
const MONO_EM = 0.6;
const SANS_EM = 0.56;
const COLUMN_GAP = 24;

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

  const lines = entries.map((d) => ({
    when: offsetLabel(d, v.anchorLabel),
    label: d.label,
  }));
  // The columns are as wide as their longest line, so the Frist never starts
  // inside the text that says when it is due.
  const whenWidth = Math.max(...lines.map((l) => l.when.length)) * SIZE * MONO_EM;
  const labelX = Math.round(PAD + whenWidth + COLUMN_GAP);
  const labelWidth = Math.max(...lines.map((l) => l.label.length)) * SIZE * SANS_EM;
  const width = Math.round(labelX + labelWidth + PAD);

  const rows = lines
    .map((l, i) => {
      const y = HEAD + i * ROW;
      return [
        `<text x="${PAD}" y="${y}" font-size="${SIZE}" fill="#4d545e" font-family="monospace">${escapeXml(
          l.when,
        )}</text>`,
        `<text x="${labelX}" y="${y}" font-size="${SIZE}" fill="#14161a">${escapeXml(l.label)}</text>`,
      ].join("");
    })
    .join("");

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="system-ui, sans-serif" role="img" aria-label="${escapeXml(
    `${v.label}: ${entries.length} Fristen`,
  )}"><rect width="${width}" height="${height}" fill="#ffffff"/><text x="${PAD}" y="${
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
