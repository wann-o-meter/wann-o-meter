import { defineConfig } from "vitest/config";

export default defineConfig({
  // Only lib. UI is checked by looking at it, and other branches keep their own
  // working trees under .claude/worktrees with their own tests.
  test: { include: ["lib/**/*.test.ts"] },
});
