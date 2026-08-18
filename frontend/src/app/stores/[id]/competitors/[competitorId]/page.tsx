"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  CompetitorListItem,
  CrossSurfaceIntentItem,
  CrossSurfaceVisibilityResponse,
  PageGapItem,
  getCompetitors,
  getCrossSurfaceVisibility,
  getPageGaps,
} from "@/lib/api";
import { classificationLabel } from "@/lib/competitor-labels";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatMetric } from "@/components/ui/StatMetric";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { surfaceLabel } from "@/components/ui/labels";
import { IconExternal } from "@/components/ui/icons";

const TOP_INTENTS_CAP = 5;

export default function CompetitorDetailPage() {
  const params = useParams<{ id: string; competitorId: string }>();
  const storeId = params.id;
  const competitorId = params.competitorId;

  const [competitor, setCompetitor] = useState<CompetitorListItem | null | undefined>(undefined);
  const [gaps, setGaps] = useState<PageGapItem[]>([]);
  const [crossSurface, setCrossSurface] = useState<CrossSurfaceVisibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [competitorsRes, gapsRes, crossSurfaceRes] = await Promise.all([
          getCompetitors(storeId),
          getPageGaps(storeId),
          getCrossSurfaceVisibility(storeId),
        ]);
        if (cancelled) return;
        const found = competitorsRes.competitors.find((c) => c.id === competitorId) ?? null;
        setCompetitor(found);
        setCrossSurface(crossSurfaceRes);
        if (found) setGaps(gapsRes.page_gaps.filter((g) => g.competitor_domain === found.domain));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storeId, competitorId]);

  if (error) return <ErrorState message={error} />;
  if (competitor === undefined) return <LoadingState />;
  if (competitor === null) return <ErrorState message="لم نجد هذا المنافس." />;

  // Real per-competitor Google-vs-AI comparison — filtered client-side from
  // the same cross-surface dataset Market/Overview already use, never a
  // second/synthetic source. Every intent here is one this competitor
  // genuinely appeared for; surfaces with no API key configured are simply
  // absent from an intent's record, never folded in as a false 0%.
  const competitorIntents = (crossSurface?.intents ?? [])
    .map((intent) => ({ intent, visibility: intent.competitor_visibility[competitor.domain] }))
    .filter((x): x is { intent: CrossSurfaceIntentItem; visibility: Record<string, number> } => !!x.visibility);

  const googleRates: number[] = [];
  const aiRates: number[] = [];
  for (const { visibility } of competitorIntents) {
    for (const [surface, rate] of Object.entries(visibility)) {
      if (surface === "google") googleRates.push(rate);
      else aiRates.push(rate);
    }
  }
  const googleSeen = googleRates.filter((value) => value > 0).length;
  const aiSeen = aiRates.filter((value) => value > 0).length;

  const topIntents = [...competitorIntents]
    .sort((a, b) => Math.max(...Object.values(b.visibility)) - Math.max(...Object.values(a.visibility)))
    .slice(0, TOP_INTENTS_CAP);

  return (
    <div className="flex flex-col gap-8 pb-16">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={competitor.is_business_competitor ? "primary" : "neutral"}>{classificationLabel(competitor.classification)}</Badge>
        </div>
        <h1 dir="ltr" className="mt-2.5 text-xl font-bold text-text">
          {competitor.domain}
        </h1>
        {competitor.discovery_reason && <p className="mt-1.5 text-sm text-text-secondary">{competitor.discovery_reason}</p>}
      </header>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatMetric label="ظهور في استعلامات Google" value={String(competitor.serp_appearances)} />
        <StatMetric label="متوسط الترتيب" value={competitor.avg_serp_rank !== null ? competitor.avg_serp_rank.toFixed(1) : "—"} />
        <StatMetric label="استُشهد به في AI" value={String(competitor.ai_citation_count)} />
        <StatMetric label="نوايا مشتركة معك" value={String(competitor.shared_stable_intents_count)} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-bold text-text">ظهوره في Google مقابل AI</h2>
        {googleRates.length > 0 || aiRates.length > 0 ? (
          <Card padding="md">
            <div className="flex flex-col gap-3.5">
              <ComparisonBar label="Google" seen={googleSeen} total={googleRates.length} />
              <ComparisonBar label="محركات AI" seen={aiSeen} total={aiRates.length} />
            </div>
          </Card>
        ) : (
          <p className="text-sm text-text-secondary">لا توجد بيانات ظهور كافية لمقارنة Google/AI لهذا المنافس بعد.</p>
        )}
      </section>

      {topIntents.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-bold text-text">أهم النوايا التي يتفوّق فيها</h2>
          <ul className="flex flex-col gap-2">
            {topIntents.map(({ intent, visibility }) => (
              <li key={intent.stable_intent_id}>
                <Card padding="sm" className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm text-text">{intent.topic}</span>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(visibility).map(([surface, rate]) => (
                      <Badge key={surface} variant="neutral">
                        {surfaceLabel(surface)}: {rate > 0 ? "ظهر في الاختبار" : "لم نرصد ظهوره"}
                      </Badge>
                    ))}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {gaps.length > 0 ? (
        <section>
          <h2 className="mb-3 text-lg font-bold text-text">لماذا يتفوق عليك؟</h2>
          <ul className="flex flex-col gap-3">
            {gaps.map((g) => (
              <li key={g.id}>
                <Card padding="md">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-text">{g.intent_topic}</p>
                    <a
                      href={g.competitor_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex shrink-0 items-center gap-1 text-xs text-text-tertiary hover:text-text-secondary"
                    >
                      عرض الصفحة
                      <IconExternal className="h-3.5 w-3.5" />
                    </a>
                  </div>
                  <p className="mt-1.5 text-sm text-text-secondary">{g.recommendation_summary}</p>
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    {g.gaps.map((item, i) => (
                      <Badge key={i} variant="warning">{item}</Badge>
                    ))}
                    {g.confidence !== null && <Badge variant="neutral">ثقة {Math.round(g.confidence * 100)}%</Badge>}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-sm text-text-secondary">لم نقارن صفحاته بصفحاتك بعد لهذا المنافس تحديدًا.</p>
      )}
    </div>
  );
}

function ComparisonBar({ label, seen, total }: { label: string; seen: number; total: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-text-secondary">
        <span>{label}</span>
        <span className="tabular">{total ? `ظهر في ${seen} من ${total} اختبارات` : "لم نقِسه بعد"}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-tint">
        {total > 0 && <div className="h-full rounded-full bg-primary" style={{ width: `${seen / total * 100}%` }} />}
      </div>
    </div>
  );
}
