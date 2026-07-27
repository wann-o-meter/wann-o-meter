// @ts-check
import { defineConfig } from 'astro/config';

import vue from '@astrojs/vue';

import sitemap from '@astrojs/sitemap';

import { includeInSitemap } from './lib/year-pages';

// https://astro.build/config
export default defineConfig({
  site: 'https://wannometer.de',
  // Opt-in per link (data-astro-prefetch), not prefetchAll: the only links
  // that need it are the year pills (see DateListControls.astro), where the
  // target is already in cache by the time you click and the swap reads as an
  // in-place filter rather than a page load.
  prefetch: true,
  // A year page outside its indexing window carries noindex, so listing it in
  // the sitemap would be a contradiction - the filter keeps the two in step.
  integrations: [vue(), sitemap({ filter: includeInSitemap })]
});