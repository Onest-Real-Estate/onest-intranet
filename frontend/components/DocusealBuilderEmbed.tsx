import { type CSSProperties, createElement, useEffect, useRef } from "react";

/**
 * Self-hosted DocuSeal often runs on plain HTTP (local Docker).
 * ``@docuseal/react`` always loads ``https://${host}/js/builder.js``, which
 * fails against a non-TLS Puma with ERR_SSL_PROTOCOL_ERROR. This wrapper loads
 * the script with the correct scheme and sets ``data-host`` for the web component.
 */
type RequiredField = {
  name: string;
  type: string;
  role: string;
};

type DocusealBuilderEmbedProps = {
  token: string;
  host: string;
  protocol?: "http" | "https";
  roles?: string[];
  requiredFields?: RequiredField[];
  withSendButton?: boolean;
  withSignYourselfButton?: boolean;
  withUploadButton?: boolean;
  onSave?: (detail: unknown) => void;
  className?: string;
  style?: CSSProperties;
};

function boolAttr(value: boolean | undefined): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  return value ? "true" : "false";
}

export function DocusealBuilderEmbed({
  token,
  host,
  protocol = "https",
  roles = [],
  requiredFields = [],
  withSendButton = true,
  withSignYourselfButton = true,
  withUploadButton = true,
  onSave,
  className = "",
  style,
}: DocusealBuilderEmbedProps) {
  const ref = useRef<HTMLElement | null>(null);
  const scriptSrc = `${protocol}://${host}/js/builder.js`;

  useEffect(() => {
    const scriptId = "docuseal-builder-script";
    const existing = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (existing && existing.getAttribute("src") !== scriptSrc) {
      existing.remove();
    }
    if (!document.getElementById(scriptId)) {
      const script = document.createElement("script");
      script.id = scriptId;
      script.async = true;
      script.src = scriptSrc;
      document.head.appendChild(script);
    }
  }, [scriptSrc]);

  useEffect(() => {
    const node = ref.current;
    if (!node || !onSave) {
      return;
    }
    const handler = (event: Event) => {
      onSave((event as CustomEvent).detail);
    };
    node.addEventListener("save", handler);
    return () => node.removeEventListener("save", handler);
  }, [onSave]);

  return createElement("docuseal-builder", {
    ref,
    className,
    style,
    "data-token": token,
    "data-host": host,
    "data-roles": roles.join(","),
    "data-required-fields": JSON.stringify(requiredFields),
    "data-with-send-button": boolAttr(withSendButton),
    "data-with-sign-yourself-button": boolAttr(withSignYourselfButton),
    "data-with-upload-button": boolAttr(withUploadButton),
  });
}
