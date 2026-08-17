import { execFileSync } from "node:child_process";

// When the content behind a page last changed. Taken from git rather than from
// a field in the yaml, because a field someone has to remember to bump is a
// field that goes stale and then lies about how fresh the page is.
//
// Node only: reads the repo at build time. Never import this from an island.
const cache = new Map<string, string | undefined>();

export interface DataChange {
  date: string;
  subject: string;
  files: string[];
}

// Every commit that touched the rules, so a visitor can see what moved and when
// without a changelog anyone has to write by hand. Only the hand-written yaml
// counts: a commit that regenerated the Feiertage changed no Frist.
export function dataChanges(paths: string[], limit = 50): DataChange[] {
  let out = "";
  try {
    out = execFileSync(
      "git",
      [
        "log",
        `-${limit}`,
        "--no-show-signature",
        "--name-only",
        // A NUL starts every commit, so the file list below it cannot be
        // confused with the next subject line.
        "--format=%x00%cI %s",
        "--",
        ...paths,
      ],
      { encoding: "utf-8" },
    );
  } catch {
    return [];
  }
  return out
    .split("\0")
    .slice(1)
    .map((block) => {
      const [head, ...rest] = block.split("\n");
      const cut = head.indexOf(" ");
      return {
        date: head.slice(0, cut),
        subject: head.slice(cut + 1),
        files: rest.filter((f) => f.startsWith("data/")),
      };
    })
    .filter((c) => c.files.length > 0);
}

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
