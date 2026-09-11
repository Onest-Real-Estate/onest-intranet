import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HeadshotRequestError,
  removeHeadshot,
  uploadHeadshot,
} from "@/components/onboarding/profile/headshot-transport";

class FakeXhr {
  static instances: FakeXhr[] = [];
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
    onprogress: null,
  };
  status = 0;
  responseText = "";
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  method = "";
  url = "";
  headers: Record<string, string> = {};
  body: FormData | null = null;

  constructor() {
    FakeXhr.instances.push(this);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }

  send(body: FormData) {
    this.body = body;
  }

  abort() {
    this.onabort?.();
  }

  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === "string" ? body : JSON.stringify(body);
    this.onload?.();
  }
}

function latest(): FakeXhr {
  const request = FakeXhr.instances.at(-1);
  if (!request) {
    throw new Error("No request was sent.");
  }
  return request;
}

const photo = () => new File(["jpeg"], "me.jpg", { type: "image/jpeg" });

describe("headshot transport", () => {
  beforeEach(() => {
    FakeXhr.instances = [];
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts the file with the CSRF token and reports real upload progress", async () => {
    const onProgress = vi.fn();
    const pending = uploadHeadshot(photo(), { csrfToken: "token", onProgress });
    const request = latest();

    expect(request.method).toBe("POST");
    expect(request.url).toBe("/account/headshot");
    expect(request.headers.Accept).toBe("application/json");
    expect(request.body?.get("csrfmiddlewaretoken")).toBe("token");
    expect(request.body?.get("headshot")).toBeInstanceOf(File);

    request.upload.onprogress?.({
      lengthComputable: true,
      loaded: 50,
      total: 100,
    } as ProgressEvent);
    expect(onProgress).toHaveBeenLastCalledWith(45);

    request.respond(200, { url: "http://testserver/account/headshot/file?v=abc" });
    await expect(pending).resolves.toBe(
      "http://testserver/account/headshot/file?v=abc",
    );
    expect(onProgress).toHaveBeenLastCalledWith(100);
  });

  it("classifies an expired session so the page can offer to sign in", async () => {
    const pending = uploadHeadshot(photo(), { csrfToken: "token" });
    latest().respond(401, { error: "authentication_required" });

    const failure = await pending.catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(HeadshotRequestError);
    expect(failure).toMatchObject({ sessionExpired: true, retryable: false });
  });

  it("passes the server's message and retry advice through", async () => {
    const unavailable = uploadHeadshot(photo(), { csrfToken: "token" });
    latest().respond(503, { error: "Photo storage is unavailable.", retryable: true });
    await expect(unavailable).rejects.toMatchObject({
      message: "Photo storage is unavailable.",
      retryable: true,
    });

    const rejected = uploadHeadshot(photo(), { csrfToken: "token" });
    latest().respond(422, {
      error: "Headshot must be at least 200×200 pixels.",
      retryable: false,
    });
    await expect(rejected).rejects.toMatchObject({ retryable: false });
  });

  it("treats a dropped connection or a non-JSON reply as retryable", async () => {
    const dropped = uploadHeadshot(photo(), { csrfToken: "token" });
    latest().onerror?.();
    await expect(dropped).rejects.toMatchObject({ retryable: true });

    const proxyError = uploadHeadshot(photo(), { csrfToken: "token" });
    latest().respond(502, "<html>Bad gateway</html>");
    await expect(proxyError).rejects.toMatchObject({ retryable: true });
  });

  it("cancels the request when its signal aborts", async () => {
    const controller = new AbortController();
    const pending = uploadHeadshot(photo(), {
      csrfToken: "token",
      signal: controller.signal,
    });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("removes the stored photo through the same endpoint", async () => {
    const pending = removeHeadshot({ csrfToken: "token" });
    const request = latest();
    expect(request.body?.get("remove")).toBe("1");
    request.respond(200, { url: null });
    await expect(pending).resolves.toBeUndefined();
  });
});
