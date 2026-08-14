import { defineConfig } from "astro/config";
import vue from "@astrojs/vue";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://wannometer.de",
  prefetch: true,
  integrations: [
    vue(),
    // Noindex pages do not belong in the sitemap.
    sitemap({ filter: (page) => !page.includes("/feedback/") }),
  ],
});
