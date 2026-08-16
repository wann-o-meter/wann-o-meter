import { execFileSync } from "node:child_process";
import { defineConfig } from "astro/config";
import vue from "@astrojs/vue";
import sitemap from "@astrojs/sitemap";

// lastmod comes from the last commit that touched the data behind a page, not
// from the build clock: a rebuild does not make the content newer.
function lastCommitDate(...paths) {
  try {
    const out = execFileSync(
      "git",
      ["log", "-1", "--no-show-signature", "--format=%cI", "--", ...paths],
      { encoding: "utf-8" },
    ).trim();
    return out || undefined;
  } catch {
    return undefined;
  }
}

const lastmodCache = new Map();
function lastmodFor(url) {
  const path = new URL(url).pathname;
  const slug = path.split("/").filter(Boolean)[0];
  const key = slug ?? "";
  if (!lastmodCache.has(key)) {
    lastmodCache.set(
      key,
      slug
        ? lastCommitDate(`data/${slug}`, "data/vorhaben.yaml")
        : lastCommitDate("data", "src/pages/index.astro"),
    );
  }
  return lastmodCache.get(key);
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
      // Noindex pages do not belong in the sitemap.
      filter: (page) => !page.includes("/feedback/"),
      serialize(item) {
        const lastmod = lastmodFor(item.url);
        return lastmod ? { ...item, lastmod } : item;
      },
    }),
  ],
});
