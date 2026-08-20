// Copies the one Inter file the site serves out of the package it came from,
// so public/fonts never drifts away from the installed version.
import { copyFileSync, mkdirSync } from "node:fs";

const src =
  "node_modules/@fontsource-variable/inter/files/inter-latin-opsz-normal.woff2";
mkdirSync("public/fonts", { recursive: true });
copyFileSync(src, "public/fonts/inter-latin.woff2");
