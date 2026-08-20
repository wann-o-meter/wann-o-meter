// The scale is only a scale as long as nothing outside tokens.css invents a
// value. This fails the build on the four properties that carry it.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = "src";
const OWNER = "src/styles/tokens.css";
// Its own document on someone else's site, so it ships without our stylesheet.
const STANDALONE = ["src/pages/embed/[vorhaben].astro"];

const RULES = [
  // A size has to name a role. calc() around a role token is still the role.
  [/font-size:(?![^;]*(var\(--t-|inherit))/g, "font-size outside the six roles"],
  [/font-weight:(?![^;]*var\(--fw-)/g, "font-weight outside the two weights"],
  [/letter-spacing:/g, "letter-spacing outside the uppercase label role"],
  [/text-transform:/g, "text-transform outside the uppercase label role"],
];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* walk(path);
    else if (/\.(css|vue|astro)$/.test(path)) yield path;
  }
}

export function tokenViolations() {
  const found = [];
  for (const path of walk(ROOT)) {
    if (path === OWNER || STANDALONE.includes(path)) continue;
    const lines = readFileSync(path, "utf8").split("\n");
    lines.forEach((line, i) => {
      for (const [pattern, why] of RULES) {
        pattern.lastIndex = 0;
        if (pattern.test(line)) found.push(`${path}:${i + 1} ${why}: ${line.trim()}`);
      }
    });
  }
  return found;
}
