import type { APIRoute } from "astro";
import { loadAllVorhaben } from "../../../../../lib/vorhaben-data";
import type { Vorhaben, VorhabenVariant } from "../../../../../lib/vorhaben-data";

// The bridge past the node:fs wall: lib/vorhaben-data.ts reads data/*.yaml at
// build time, the ICS worker (workers/ics/) runs at the edge and can't. One
// file per variant rather than one blob per Vorhaben, because the bundesweit
// deadlines are concatenated into every variant - a combined file would ship
// them 40 times over for a worker that only ever needs one.
export function getStaticPaths() {
  return loadAllVorhaben().flatMap((v) =>
    v.variants.map((variant) => ({
      params: { path: `${v.slug}/${variant.slug}` },
      props: { meta: v as Vorhaben, variant },
    })),
  );
}

export const GET: APIRoute = ({ props }) => {
  const { meta, variant } = props as { meta: Vorhaben; variant: VorhabenVariant };
  const body = {
    slug: meta.slug,
    vorhaben: meta.vorhaben,
    anchorLabel: meta.anchorLabel,
    variant,
  };
  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
