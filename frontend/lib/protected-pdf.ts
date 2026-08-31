/** Load a session-protected PDF for pdf.js (main-thread fetch with cookies). */
export async function loadProtectedPdfBytes(pdfUrl: string): Promise<ArrayBuffer> {
  const response = await fetch(pdfUrl, {
    credentials: "same-origin",
    headers: { Accept: "application/pdf" },
  });
  if (response.status === 401 || response.status === 403) {
    throw new Error("You do not have permission to view this PDF.");
  }
  if (response.status === 404) {
    throw new Error("This PDF is not available yet. Upload a source file and save.");
  }
  if (!response.ok) {
    throw new Error("Could not load the template PDF.");
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/html")) {
    throw new Error("Could not load the template PDF. Sign in again and retry.");
  }
  return response.arrayBuffer();
}
