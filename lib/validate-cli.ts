#!/usr/bin/env bun
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
