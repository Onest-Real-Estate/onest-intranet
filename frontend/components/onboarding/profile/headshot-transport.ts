import { routes } from "@/lib/routes";

/**
 * Talks to the shared, protected headshot endpoint (`headshot_upload`).
 *
 * XMLHttpRequest rather than `fetch` for one reason: upload progress. The
 * endpoint answers in JSON, including when the session has expired, so every
 * failure is classified here into something the page can say and act on.
 */

export class HeadshotRequestError extends Error {
  readonly retryable: boolean;
  readonly sessionExpired: boolean;

  constructor(message: string, { retryable = false, sessionExpired = false } = {}) {
    super(message);
    this.name = "HeadshotRequestError";
    this.retryable = retryable;
    this.sessionExpired = sessionExpired;
  }
}

export interface HeadshotRequestOptions {
  csrfToken: string;
  signal?: AbortSignal;
  onProgress?: (percent: number) => void;
}

const SESSION_EXPIRED =
  "Your session expired. Sign in again; everything you already saved is kept.";
const NETWORK_FAILURE =
  "We could not reach the server. Check your connection, then retry.";

function parseBody(text: string): {
  url?: string | null;
  error?: string;
  retryable?: boolean;
} {
  try {
    const parsed = JSON.parse(text) as unknown;
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function send(body: FormData, options: HeadshotRequestOptions): Promise<string | null> {
  body.append("csrfmiddlewaretoken", options.csrfToken);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", routes.headshot_upload());
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        // Hold the last few percent until the server has validated and stored it.
        options.onProgress?.(Math.round((event.loaded / event.total) * 90));
      }
    };
    xhr.onload = () => {
      const payload = parseBody(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        options.onProgress?.(100);
        resolve(payload.url ?? null);
        return;
      }
      if (xhr.status === 401 || xhr.status === 403) {
        reject(new HeadshotRequestError(SESSION_EXPIRED, { sessionExpired: true }));
        return;
      }
      reject(
        new HeadshotRequestError(
          payload.error ?? "The photo could not be saved. Try again.",
          { retryable: payload.retryable ?? xhr.status >= 500 },
        ),
      );
    };
    xhr.onerror = () =>
      reject(new HeadshotRequestError(NETWORK_FAILURE, { retryable: true }));
    xhr.onabort = () =>
      reject(new DOMException("The upload was cancelled.", "AbortError"));

    if (options.signal?.aborted) {
      reject(new DOMException("The upload was cancelled.", "AbortError"));
      return;
    }
    options.signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(body);
  });
}

export async function uploadHeadshot(
  file: File,
  options: HeadshotRequestOptions,
): Promise<string> {
  const body = new FormData();
  body.append("headshot", file);
  const url = await send(body, options);
  if (!url) {
    throw new HeadshotRequestError("The server did not confirm the upload. Retry.", {
      retryable: true,
    });
  }
  return url;
}

export async function removeHeadshot(options: HeadshotRequestOptions): Promise<void> {
  const body = new FormData();
  body.append("remove", "1");
  await send(body, options);
}
