import type { AnnouncementBlock, AnnouncementInlineSpan } from "@/types";

/**
 * An announcement body, rendered from the server's block tree.
 *
 * There is no `dangerouslySetInnerHTML` here, and there is no HTML in the
 * payload for one to consume. The server hands over a structured tree — see
 * `apps/announcements/richtext.py` — and every node becomes a real React
 * element. A `<script>` an author typed arrives as `{type: "text", value:
 * "<script>…"}` and is rendered as the characters it is.
 *
 * That is the whole safety argument, and it is structural: unsafe markup is not
 * filtered out of this component, it never reaches a code path that could
 * execute it. Link destinations were checked server-side against one allowlist
 * (https, mailto, hub-relative); a refused link arrived as plain text, so there
 * is nothing for this component to re-check.
 */
export function AnnouncementBody({
  blocks,
  className,
}: {
  blocks: AnnouncementBlock[];
  className?: string;
}) {
  if (blocks.length === 0) {
    return null;
  }
  return (
    <div className={className ?? "grid gap-4 text-sm leading-6"}>
      {blocks.map((block, index) => (
        // Blocks have no stable identity of their own — they are a rendering of
        // one text field — so position is the honest key. The list is replaced
        // wholesale whenever the body changes, never reordered in place.
        <Block key={index} block={block} />
      ))}
    </div>
  );
}

function Block({ block }: { block: AnnouncementBlock }) {
  switch (block.type) {
    case "heading": {
      // The article's own title is the page heading, so a body heading starts
      // one level below it and never competes for the document outline.
      const Tag = block.level === 2 ? "h3" : "h4";
      return (
        <Tag className="text-foreground text-base leading-6 font-semibold">
          <Spans spans={block.spans ?? []} />
        </Tag>
      );
    }
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag
          className={
            block.ordered ? "grid list-decimal gap-1 pl-5" : "grid list-disc gap-1 pl-5"
          }
        >
          {(block.items ?? []).map((item, index) => (
            <li key={index}>
              <Spans spans={item} />
            </li>
          ))}
        </Tag>
      );
    }
    case "quote":
      return (
        <blockquote className="border-border text-muted-foreground border-l-2 pl-4 italic">
          <Spans spans={block.spans ?? []} />
        </blockquote>
      );
    default:
      return (
        <p>
          <Spans spans={block.spans ?? []} />
        </p>
      );
  }
}

function Spans({ spans }: { spans: AnnouncementInlineSpan[] }) {
  return (
    <>
      {spans.map((span, index) => {
        if (span.type === "strong") {
          return (
            <strong key={index} className="font-semibold">
              {span.value}
            </strong>
          );
        }
        if (span.type === "em") {
          return <em key={index}>{span.value}</em>;
        }
        if (span.type === "link" && span.href) {
          const external = !span.href.startsWith("/");
          return (
            <a
              key={index}
              href={span.href}
              // Plain anchor rather than an Inertia Link: an external
              // destination is not a hub page, and a hub-relative body link is
              // rare enough that a full navigation is the honest behaviour.
              target={external ? "_blank" : undefined}
              rel={external ? "noopener noreferrer" : undefined}
              className="text-primary underline underline-offset-2"
            >
              {span.value}
              {external ? <span className="sr-only"> (opens in a new tab)</span> : null}
            </a>
          );
        }
        return <span key={index}>{span.value}</span>;
      })}
    </>
  );
}
