import { Badge } from "./Badge";
import { classificationLabel } from "@/lib/competitor-labels";

/** Domain + classification badge — was reimplemented independently on the
 * Competitors, Market (cross-surface), and Recommendation-detail pages.
 * Section 9's requirement (distinguish direct competitor from marketplace/
 * publisher/irrelevant clearly, everywhere) is now enforced by construction:
 * every caller gets the same visual language from one place. */
export function CompetitorBadge({
  domain,
  classification,
  isBusinessCompetitor,
}: {
  domain: string;
  classification: string;
  isBusinessCompetitor: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <span dir="ltr" className="text-sm font-medium text-text">
        {domain}
      </span>
      <Badge variant={isBusinessCompetitor ? "primary" : "neutral"}>{classificationLabel(classification)}</Badge>
    </span>
  );
}
