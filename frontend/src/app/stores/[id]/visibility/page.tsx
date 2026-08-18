"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AlertItem, IntentListItem, StoreDetail, SurfaceMetrics, getAIVisibility, getAlerts, getIntents, getStore } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatMetric } from "@/components/ui/StatMetric";
import { ChangeFeed } from "@/components/ui/ChangeFeed";
import { EmptyState, ErrorState, LoadingState, NotMeasuredYet } from "@/components/ui/States";
import { surfaceLabel } from "@/components/ui/labels";
import { IconEye } from "@/components/ui/icons";

export default function VisibilityPage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const [detail, setDetail] = useState<StoreDetail | null>(null);
  const [bySurface, setBySurface] = useState<SurfaceMetrics[]>([]);
  const [unavailableSurfaces, setUnavailableSurfaces] = useState<string[]>([]);
  const [intents, setIntents] = useState<IntentListItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [storeRes, aiVisRes, intentsRes, alertsRes] = await Promise.all([
          getStore(storeId),
          getAIVisibility(storeId),
          getIntents(storeId),
          getAlerts(storeId),
        ]);
        if (cancelled) return;
        setDetail(storeRes);
        setBySurface(aiVisRes.by_surface);
        setUnavailableSurfaces(aiVisRes.unavailable_surfaces);
        setIntents(intentsRes.intents);
        setAlerts(alertsRes.alerts);
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

  const google = detail.visibility_summary?.ranking_coverage ?? null;
  const ai = detail.ai_visibility_summary?.mention_rate ?? null;
  const scores = [google, ai].filter((v): v is number => v !== null);
  const composite = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null;

  const ranked = intents.filter((i) => i.client_rank !== null).sort((a, b) => (a.client_rank ?? 99) - (b.client_rank ?? 99));
  const strongest = ranked.slice(0, 5);
  const weakest = intents.filter((i) => i.client_rank === null).slice(0, 5);

  return (
    <div className="flex flex-col gap-9">
      <div>
        <h1 className="text-xl font-bold text-text">الظهور</h1>
        <p className="mt-1 text-sm text-text-secondary">أين تظهر، أين لا تظهر، وعبر أي محرك — بيانات حقيقية فقط، لا محرك غير مُقاس يُحتسب كصفر.</p>
      </div>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatMetric label="مؤشر الظهور العام" value={composite !== null ? `${Math.round(composite * 100)}%` : "—"} />
        <StatMetric label="ظهور Google" value={google !== null ? `${Math.round(google * 100)}%` : "—"} />
        <StatMetric label="ظهور AI (كل المحركات)" value={ai !== null ? `${Math.round(ai * 100)}%` : "—"} />
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold text-text">الظهور حسب المحرك</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card padding="md">
            <p className="text-sm text-text-secondary">Google</p>
            <p className="tabular mt-1 text-2xl font-semibold text-text">
              {google !== null ? `${Math.round(google * 100)}%` : "—"}
            </p>
            <p className="mt-1 text-xs text-text-tertiary">نسبة النوايا ضمن أفضل 10 نتائج</p>
          </Card>
          {bySurface.map((s) => (
            <Card key={s.surface} padding="md">
              <p className="text-sm text-text-secondary">{surfaceLabel(s.surface)}</p>
              <p className="tabular mt-1 text-2xl font-semibold text-text">{Math.round(s.mention_rate * 100)}%</p>
              <p className="mt-1 text-xs text-text-tertiary">
                {s.search_enabled || s.grounding_enabled ? "بحث حي (grounded)" : "معرفة النموذج الأساسية فقط"}
              </p>
            </Card>
          ))}
          {unavailableSurfaces.map((s) => (
            <Card key={s} padding="md" className="border-dashed">
              <p className="text-sm text-text-secondary">{surfaceLabel(s)}</p>
              <p className="mt-1">
                <NotMeasuredYet label="غير مُفعَّل" />
              </p>
              <p className="mt-1 text-xs text-text-tertiary">لا يوجد مفتاح API لهذا المحرك بعد</p>
            </Card>
          ))}
        </div>
      </section>

      {(strongest.length > 0 || weakest.length > 0) && (
        <section className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <h2 className="mb-3 text-base font-semibold text-text">أقوى المواضيع ظهورًا</h2>
            {strongest.length === 0 ? (
              <p className="text-sm text-text-secondary">لا توجد نوايا ظاهرة ضمن أفضل 10 نتائج بعد.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {strongest.map((i) => (
                  <li key={i.id}>
                    <Card padding="sm" className="flex items-center justify-between">
                      <span className="text-sm text-text">{i.topic}</span>
                      <Badge variant="success">ترتيب {i.client_rank}</Badge>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h2 className="mb-3 text-base font-semibold text-text">أضعف المواضيع ظهورًا</h2>
            {weakest.length === 0 ? (
              <p className="text-sm text-text-secondary">لا توجد نوايا ضعيفة الظهور حاليًا — تغطية جيدة.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {weakest.map((i) => (
                  <li key={i.id}>
                    <Card padding="sm" className="flex items-center justify-between">
                      <span className="text-sm text-text">{i.topic}</span>
                      <Badge variant="danger">غير ظاهر</Badge>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {/* Section 6/12 — no historical trend endpoint exists (Product UI
          Inventory finding); a real, timestamped alert feed stands in for
          a fabricated line chart. */}
      <section>
        <h2 className="mb-3 text-base font-semibold text-text">آخر التغيرات</h2>
        {alerts.length === 0 ? (
          <EmptyState icon={<IconEye className="h-5 w-5" />} title="لا توجد تغيرات مسجَّلة بعد" description="سنعرض هنا أي تغيّر ملحوظ في ظهورك أول بأول." />
        ) : (
          <ChangeFeed alerts={alerts} storeId={storeId} limit={10} />
        )}
      </section>
    </div>
  );
}
