import { type CSSProperties, createElement, useEffect, useRef } from "react";

/**
 * Like ``@docuseal/react`` ``DocusealForm``, but loads ``form.js`` with the
 * scheme from ``DOCUSEAL_BASE_URL`` so local HTTP DocuSeal does not hit
 * ERR_SSL_PROTOCOL_ERROR.
 */
type DocusealFormEmbedProps = {
  src: string;
  host: string;
  protocol?: "http" | "https";
  email?: string;
  name?: string;
  allowToResubmit?: boolean;
  onComplete?: (detail: unknown) => void;
  className?: string;
  style?: CSSProperties;
};

export function DocusealFormEmbed({
  src,
  host,
  protocol = "https",
  email = "",
  name = "",
  allowToResubmit = true,
  onComplete,
  className = "",
  style,
}: DocusealFormEmbedProps) {
  const ref = useRef<HTMLElement | null>(null);
  const scriptSrc = `${protocol}://${host}/js/form.js`;

  useEffect(() => {
    const scriptId = "docuseal-form-script";
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
    if (!node || !onComplete) {
      return;
    }
    const handler = (event: Event) => {
      onComplete((event as CustomEvent).detail);
    };
    node.addEventListener("completed", handler);
    return () => node.removeEventListener("completed", handler);
  }, [onComplete]);

  return createElement("docuseal-form", {
    ref,
    className,
    style,
    "data-src": src,
    "data-host": host,
    "data-email": email,
    "data-name": name,
    "data-allow-to-resubmit": allowToResubmit ? "true" : "false",
  });
}
