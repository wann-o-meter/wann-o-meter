#!/usr/bin/env bun
// Validates a page data file (JSON) against the same Zod schema the Astro
// build uses (pageDataSchema in ./pages-schema.ts). Exists so the Python
// pipeline (pipeline/core/validate.py) does NOT have to define "valid" a
// second time - a JSON schema export (zod-to-json-schema) was the more
// obvious route, but is empty/broken under Zod v4 (verified empirically:
// even a trivial schema exports {}). Calling the same Zod object directly
// has zero drift risk.
import { readFileSync } from "node:fs";
import { pageDataSchema } from "./pages-schema";

const path = process.argv[2];
if (!path) {
  console.error("Usage: bun run lib/validate-cli.ts <file.json>");
  process.exit(2);
}

const data = JSON.parse(readFileSync(path, "utf-8"));
const result = pageDataSchema.safeParse(data);

if (!result.success) {
  console.error(JSON.stringify(result.error.issues, null, 2));
  process.exit(1);
}
