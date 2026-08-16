/**
 * lint-staged configuration.
 *
 * The `tsc` task uses a function signature so lint-staged does NOT append the
 * staged file list to the command — tsc ignores tsconfig.json when given
 * explicit input files, so it must run as a whole-project check.
 */
export default {
  "*.py": [
    "uv run ruff format --force-exclude",
    "uv run ruff check --fix --force-exclude",
  ],
  "*.{ts,tsx,js,jsx,mjs,cjs}": [
    "pnpm exec biome check --write",
    () => "pnpm exec tsc -p tsconfig.json --noEmit",
  ],
};
