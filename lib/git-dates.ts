import { execFileSync } from "node:child_process";

// When the content behind a page last changed. Taken from git rather than from
// a field in the yaml, because a field someone has to remember to bump is a
// field that goes stale and then lies about how fresh the page is.
//
// Node only: reads the repo at build time. Never import this from an island.
const cache = new Map<string, string | undefined>();

export function lastChanged(...paths: string[]): string | undefined {
  const key = paths.join("\0");
  if (!cache.has(key)) {
    let out: string | undefined;
    try {
      out =
        execFileSync(
          "git",
          ["log", "-1", "--no-show-signature", "--format=%cI", "--", ...paths],
          { encoding: "utf-8" },
        ).trim() || undefined;
    } catch {
      out = undefined;
    }
    cache.set(key, out);
  }
  return cache.get(key);
}
