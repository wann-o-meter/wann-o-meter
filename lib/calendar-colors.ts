// Muted "ink" colors instead of bright marker colors - matches the site's
// paper/document tone (see src/styles/global.css). Shared by Kalender.vue
// (assigns COLORS[layers.length % COLORS.length] as each layer is added) and
// the homepage preview (src/pages/index.astro), so the preview's fixed
// layers show the same colors a user would see adding them in that order on
// the real page - kept in one place instead of two copies drifting apart.
export const COLORS = [
  "#3c5a80", "#6b7d3d", "#8a5a2b", "#5c4a72", "#2f7565",
  "#9c4f3c", "#4a5a6b", "#7d5a3c", "#3c6b6b", "#6b3c52",
];
