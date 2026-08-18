"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CompetitorListItem, OpportunityItem, RecommendationItem, StoreDetail, getCompetitors, getOpportunities, getRecommendations, getStore } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { ConfidenceBadge } from "@/components/ui/labels";
import { classificationLabel } from "@/lib/competitor-labels";
import { IconPrint, IconSearch } from "@/components/ui/icons";

export default function ReportsPage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const [detail, setDetail] = useState<StoreDetail | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [storeRes, recsRes, oppsRes, competitorsRes] = await Promise.all([
          getStore(storeId),
          getRecommendations(storeId),
          getOpportunities(storeId),
          getCompetitors(storeId),
        ]);
        if (cancelled) return;
        setDetail(storeRes);
        setRecommendations(recsRes.recommendations);
        setOpportunities(oppsRes.opportunities);
        setCompetitors(competitorsRes.competitors);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  if (error) return <ErrorState message={error} />;
  if (!detail) return <LoadingState />;

  const primaryRecs = recommendations.filter((r) => r.is_primary).sort((a, b) => b.priority_score - a.priority_score);
  const topOpportunities = opportunities.filter((o) => o.status === "open").sort((a, b) => b.priority_score - a.priority_score).slice(0, 5);
  const topCompetitors = competitors.filter((c) => c.is_business_competitor).sort((a, b) => b.serp_appearances - a.serp_appearances).slice(0, 5);
  const google = detail.visibility_summary?.ranking_coverage ?? null;
  const ai = detail.ai_visibility_summary?.mention_rate ?? null;

  return (
    <div className="flex flex-col gap-8 pb-16">
      <div className="no-print flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-text">التقرير الموجز</h1>
          <p className="mt-1 text-sm text-text-secondary">ملخص قابل للطباعة والمشاركة من أحدث بيانات متجرك.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => window.print()}>
          <IconPrint className="h-4 w-4" />
          طباعة / تصدير PDF
        </Button>
      </div>

      <header className="border-b border-border pb-4">
        <p dir="ltr" className="text-sm text-text-secondary">
          {detail.url}
        </p>
        <p className="mt-1 text-xs text-text-tertiary">
          تاريخ التقرير: {new Date().toLocaleDateString("ar")}
        </p>
      </header>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <ReportStat label="ظهور Google" value={google !== null ? `${Math.round(google * 100)}%` : "—"} />
        <ReportStat label="ظهور AI" value={ai !== null ? `${Math.round(ai * 100)}%` : "—"} />
        <ReportStat label="فرص مفتوحة" value={String(opportunities.filter((o) => o.status === "open").length)} />
        <ReportStat label="منافسون مباشرون" value={String(competitors.filter((c) => c.is_business_competitor).length)} />
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold text-text">أهم التوصيات ({primaryRecs.length})</h2>
        {primaryRecs.length === 0 ? (
          <p className="text-sm text-text-secondary">لا توجد توصيات ذات أولوية حاليًا.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {primaryRecs.map((r) => (
              <li key={r.id}>
                <Card padding="sm">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold text-text">{r.title}</p>
                    <ConfidenceBadge tier={r.confidence_tier} />
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">{r.why_it_matters}</p>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold text-text">أبرز الفرص</h2>
        <ul className="flex flex-col gap-2.5">
          {topOpportunities.map((o) => (
            <li key={o.id}>
              <Card padding="sm">
                <p className="text-sm font-semibold text-text">{o.title}</p>
                <p className="mt-1 text-sm text-text-secondary">{o.description}</p>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold text-text">أبرز المنافسين</h2>
        <ul className="flex flex-wrap gap-2">
          {topCompetitors.map((c) => (
            <li key={c.id}>
              <Badge variant="primary">
                <span dir="ltr">{c.domain}</span> — {classificationLabel(c.classification)}
              </Badge>
            </li>
          ))}
        </ul>
      </section>

      <div className="no-print border-t border-border pt-6">
        <Link href={`/stores/${storeId}/research`} className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text">
          <IconSearch className="h-4 w-4" />
          تفاصيل تقنية عن عملية البحث (للمهتمين)
        </Link>
      </div>
    </div>
  );
}

function ReportStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-text-secondary">{label}</p>
      <p className="tabular mt-1 text-2xl font-semibold text-text">{value}</p>
    </div>
  );
}
