import type { ComponentType } from "react";

import { MicrosoftLogo } from "@/components/MicrosoftLogo";
import { SkySlopeLogo } from "@/components/SkySlopeLogo";
import loftyMark from "@/images/lofty.png";
import rprMark from "@/images/rpr.png";

interface BrandMarkDefinition {
  Component: ComponentType<{ className?: string }>;
  /**
   * True when the artwork ships its own background — RPR's mark lives on a
   * black rounded tile. Those fill the launcher tile instead of sitting inside
   * the tinted well, because a vendor's tile inside our tile is two nested
   * squares and reads as a mistake.
   */
  bleed?: boolean;
}

function RasterMark({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  // `alt=""`: the launcher already names the vendor in text beside the mark,
  // so a screen reader announcing it twice is noise, not access.
  return <img src={src} alt={alt} className={className} loading="lazy" />;
}

function LoftyLogo({ className }: { className?: string }) {
  return <RasterMark src={loftyMark} alt="" className={className} />;
}

function RprLogo({ className }: { className?: string }) {
  return <RasterMark src={rprMark} alt="" className={className} />;
}

/**
 * Vendors whose **real** mark this bundle ships.
 *
 * A Quick Access launcher normally draws an approved Lucide glyph — a shield
 * for a compliance tool, a contact card for a CRM. That is a *category* mark,
 * not the vendor's identity, and it stays the right default for any vendor
 * whose official artwork the project does not hold: a silhouette nobody
 * mistakes for a logo beats an approximation of one.
 *
 * Every mark below is the vendor's own published artwork, used to label a link
 * to that vendor's product. Nothing here is drawn from memory — a lookalike
 * would put a fake trademark in the product, and a wrong logo reads as worse
 * craft than an honest generic icon.
 *
 * Adding one is two lines: a component beside `MicrosoftLogo`, and an entry
 * here under the icon key. The key must also exist in
 * `QUICK_ACCESS_ICON_KEYS` and in the backend allowlist
 * (`apps/web/quick_access/catalog.py`), which a test pins to this file.
 */
export const BRAND_MARKS: Record<string, BrandMarkDefinition> = {
  microsoft: { Component: MicrosoftLogo },
  lofty: { Component: LoftyLogo },
  skyslope: { Component: SkySlopeLogo },
  rpr: { Component: RprLogo, bleed: true },
};

export function brandMark(iconKey: string): BrandMarkDefinition | undefined {
  return BRAND_MARKS[iconKey];
}

export const BRAND_MARK_KEYS: readonly string[] = Object.keys(BRAND_MARKS);
