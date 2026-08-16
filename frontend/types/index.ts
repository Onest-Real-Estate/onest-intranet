export interface User {
  id: number;
  email: string;
  name: string;
  /** Django auth permission codenames, e.g. "user.view_user". */
  permissions: string[];
}

/**
 * Props available on every Inertia page. `user` and `csrfToken` are shared by
 * `web.middleware.InertiaShareMiddleware`; pages can extend this interface.
 */
export interface PageProps {
  user: User | null;
  csrfToken: string;
  [key: string]: unknown;
}
