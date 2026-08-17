import { existsSync } from "node:fs";
import { defineConfig } from "astro/config";
import vue from "@astrojs/vue";
import sitemap from "@astrojs/sitemap";
import { lastChanged } from "./lib/git-dates.ts";
import { noindexPaths } from "./lib/vorhaben-routes.ts";

// lastmod comes from the last commit that touched the data behind a page, not
// from the build clock: a rebuild does not make the content newer. Narrow
// enough that two pages sharing no yaml do not share a date either, otherwise
// every page moves whenever any of them does and the whole signal is noise.
function sourcesFor(url) {
  const [first, second] = new URL(url).pathname.split("/").filter(Boolean);
  if (!first) return ["data/vorhaben.yaml", "src/pages/index.astro"];
  // A year page reads the same yaml as its parent, so both move together.
  if (first === "frist") return [`data/fristen/${second}.yaml`, "src/pages/frist"];
  if (second) return [`data/${first}/${second}.yaml`, `data/${first}/_bundesweit.yaml`];
  const dir = `data/${first}`;
  return existsSync(dir) ? [dir] : [`src/pages/${first}.astro`];
}

export default defineConfig({
  site: "https://wannometer.de",
  prefetch: true,
  // The two stylesheets are 10 KiB gzipped and block the first paint for a
  // whole round trip on a slow connection. Inlined they cost about 7 KiB per
  // page and no round trip, which is the better trade for a visitor who
  // arrives from a search result and reads one page.
  build: { inlineStylesheets: "always" },
  integrations: [
    vue(),
    sitemap({
      // Noindex pages do not belong in the sitemap. Same rule, one source: a
      // place page without a local fact is noindex and stays out of here too.
      filter: (page) =>
        !page.includes("/feedback/") &&
        !noindexPaths().some((path) => new URL(page).pathname === path),
      serialize(item) {
        const lastmod = lastChanged(...sourcesFor(item.url));
        return lastmod ? { ...item, lastmod } : item;
      },
    }),
  ],
});
