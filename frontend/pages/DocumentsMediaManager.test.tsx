import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DocumentsMediaManager from "@/pages/DocumentsMediaManager";
import type { DocumentsAdminFileItem, DocumentsMediaManagerPageProps } from "@/types";

const routerPost = vi.fn();
const routerReload = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    post: (...args: unknown[]) => routerPost(...args),
    reload: (...args: unknown[]) => routerReload(...args),
  },
  usePage: () => ({ props: pageProps }),
}));

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

let pageProps: DocumentsMediaManagerPageProps;

function file(overrides: Partial<DocumentsAdminFileItem> = {}): DocumentsAdminFileItem {
  const id = overrides.id ?? 1;
  return {
    id,
    displayName: "form.pdf",
    mediaType: "application/pdf",
    byteSize: 2048,
    checksum: "a".repeat(64),
    url: `/operations/documents/files/${id}`,
    isReadable: true,
    processingState: "ready",
    isActive: true,
    sortOrder: 0,
    ...overrides,
  };
}

function props(
  overrides: Partial<DocumentsMediaManagerPageProps> = {},
): DocumentsMediaManagerPageProps {
  return {
    document: {
      id: 7,
      name: "Exclusive buyer agreement",
      status: "draft",
      version: "t",
    },
    files: [],
    limits: {
      document: {
        extensions: [".pdf", ".docx", ".txt"],
        maxBytes: 20 * 1024 * 1024,
        maxCount: 10,
      },
    },
    capabilities: { canAuthor: true, canPublish: true, canRetire: true },
    validation: { fields: {}, form: [] },
    ...overrides,
  } as DocumentsMediaManagerPageProps;
}

beforeEach(() => {
  routerPost.mockClear();
  routerReload.mockClear();
  pageProps = props();
});

describe("DocumentsMediaManager", () => {
  it("shows an empty state before anything is attached", () => {
    render(<DocumentsMediaManager />);
    expect(screen.getByText("No files yet")).toBeInTheDocument();
    expect(screen.getByText(/10 files maximum/)).toBeInTheDocument();
  });

  it("labels a file that is still being checked", () => {
    pageProps = props({
      files: [file({ processingState: "pending" })],
    });
    render(<DocumentsMediaManager />);
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("hides remove and reorder once the version is published", () => {
    pageProps = props({
      document: {
        id: 7,
        name: "Exclusive buyer agreement",
        status: "published",
        version: "t",
      },
      files: [file()],
    });
    render(<DocumentsMediaManager />);
    expect(
      screen.queryByRole("button", { name: /Remove form.pdf/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Published files are immutable/i)).toBeInTheDocument();
  });
});
