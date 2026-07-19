import { configDefaults, defineConfig } from "vitest/config";

// Extends (not replaces) vitest's default excludes - without this, any
// Claude Code agent worktree living under .claude/worktrees/ (a full repo
// copy, created for isolated background-agent work) gets its test files
// discovered too, silently doubling every test file/count for as long as
// the worktree exists on disk.
export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, ".claude/**"],
  },
});
