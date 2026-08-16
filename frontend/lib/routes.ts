import URLS from "@/types/routes";

/**
 * Type-safe Django URL reversal, generated from the Django URLconf by
 * django-typescript-routes:
 *
 *   pnpm run routes:generate
 *
 * Usage: `routes.dashboard()` or `routes["subscription-success"](username, pk)`.
 */
export const routes = URLS;
