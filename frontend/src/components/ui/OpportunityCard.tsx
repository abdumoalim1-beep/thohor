import { OpportunityItem } from "@/lib/api";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { effortLabel, PriorityBadge } from "./labels";

export const OPPORTUNITY_TYPE_LABELS: Record<string, string> = {
  missing_landing_page: "فجوة محتوى مقابل منافس",
  google_visibility_gap: "ضعف ظهور في Google",
  ai_citation_gap: "غياب عن إجابات AI",
  category_visibility_gap: "ضعف ظهور فئة كاملة",
};

export function impactLevel(impact: number): "high" | "medium" | "low" {
  if (impact >= 0.7) return "high";
  if (impact >= 0.4) return "medium";
  return "low";
}

const IMPACT_LABEL: Record<"high" | "medium" | "low", string> = { high: "مرتفع", medium: "متوسط", low: "منخفض" };

/** Shared between the standalone /opportunities route and the secondary
 * "إشارات لم تتحول لتوصية بعد" section on /recommendations — a single
 * card definition so the two never drift apart. */
export function OpportunityCard({ opportunity, compact }: { opportunity: OpportunityItem; compact?: boolean }) {
  const impact = typeof opportunity.score_breakdown.impact === "number" ? opportunity.score_breakdown.impact : null;

  return (
    <li>
      <Card padding={compact ? "sm" : "md"}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-medium text-text-tertiary">{OPPORTUNITY_TYPE_LABELS[opportunity.opportunity_type] ?? opportunity.opportunity_type}</p>
            <p className="mt-0.5 font-semibold text-text">{opportunity.title}</p>
          </div>
          {impact !== null && <PriorityBadge level={impactLevel(impact)} label={`أثر ${IMPACT_LABEL[impactLevel(impact)]}`} />}
        </div>
        {!compact && <p className="mt-1.5 text-sm text-text-secondary">{opportunity.description}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="neutral">ثقة {Math.round(opportunity.confidence * 100)}%</Badge>
          <Badge variant="neutral">{effortLabel(opportunity.effort_estimate)}</Badge>
          <Badge variant="neutral">الأولوية {Math.round(opportunity.priority_score)}</Badge>
          {opportunity.affected_intents.length > 0 && (
            <span className="text-text-tertiary">{opportunity.affected_intents.length} نية بحث متأثرة</span>
          )}
          {opportunity.competitors.length > 0 && <span className="text-text-tertiary">{opportunity.competitors.length} منافس مرتبط</span>}
        </div>
      </Card>
    </li>
  );
}
