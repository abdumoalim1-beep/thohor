"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  VisibilityQuestionItem,
  VisibilityRunDetail,
  getLatestVisibilityRun,
  triggerVisibilityRun,
} from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge, BadgeVariant } from "@/components/ui/Badge";
import { StatMetric } from "@/components/ui/StatMetric";
import { EmptyState, ErrorState, LoadingState, NotMeasuredYet } from "@/components/ui/States";
import { IconChevronDown, IconSpark } from "@/components/ui/icons";

const CATEGORY_LABELS: Record<string, string> = {
  recommendation: "توصية", best: "الأفضل", comparison: "مقارنة", alternatives: "بدائل",
  product_discovery: "اكتشاف منتج", local: "محلي", problem_solution: "حل مشكلة",
  occasion: "مناسبة", price: "سعر",
};

const MENTION_LABELS: Record<string, { label: string; variant: BadgeVariant }> = {
  recommended: { label: "تمت التوصية بها", variant: "success" },
  mere_mention: { label: "ذُكرت فقط", variant: "info" },
  comparison_inclusion: { label: "ضمن مقارنة", variant: "warning" },
  warned_against: { label: "تحذير منها", variant: "danger" },
  not_mentioned: { label: "لم تُذكر", variant: "neutral" },
};

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function deltaLabel(value: number | null | undefined): { trend: "up" | "down" | "flat"; label: string } | null {
  if (value === null || value === undefined) return null;
  if (Math.abs(value) < 0.005) return { trend: "flat", label: "بدون تغيّر عن الأسبوع الماضي" };
  return {
    trend: value > 0 ? "up" : "down",
    label: `${value > 0 ? "+" : ""}${Math.round(value * 100)}% عن الأسبوع الماضي`,
  };
}

export default function AIAnswersPage() {
  const params = useParams<{ id: string }>();
  const storeId = params.id;

  const [data, setData] = useState<VisibilityRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const load = async () => {
    try {
      const res = await getLatestVisibilityRun(storeId);
      setData(res);
      setError(null);
      if (res.status === "running") {
        setTimeout(load, 5000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  const onTrigger = async () => {
    setTriggering(true);
    try {
      await triggerVisibilityRun(storeId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTriggering(false);
    }
  };

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState />;

  return (
    <div className="flex flex-col gap-9">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text">ظهورك في إجابات الذكاء الاصطناعي</h1>
          <p className="mt-1 text-sm text-text-secondary">
            نسأل ChatGPT نفس الأسئلة التي يطرحها عملاؤك، ونرصد أين يظهر متجرك ومن يظهر قبلك.
          </p>
        </div>
        <button
          onClick={onTrigger}
          disabled={triggering || data.status === "running"}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:opacity-50"
        >
          <IconSpark className="h-4 w-4" />
          {data.status === "running" ? "قياس جارٍ الآن…" : "تشغيل قياس جديد"}
        </button>
      </div>

      {data.status === "no_run_yet" && (
        <EmptyState
          title="لم نقِس ظهورك على الذكاء الاصطناعي بعد"
          description="اضغط «تشغيل قياس جديد» لنسأل ChatGPT أسئلة عملائك الحقيقية ونرصد النتائج."
        />
      )}

      {data.status === "running" && (
        <LoadingState label="نسأل ChatGPT الآن ونحلل الإجابات — قد يستغرق هذا بضع دقائق…" />
      )}

      {data.status === "completed" && data.summary && (
        <>
          <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatMetric
              label="نسبة الظهور"
              value={pct(data.summary.mention_rate)}
              trend={deltaLabel(data.summary.week_over_week?.mention_rate_delta)?.trend}
              trendLabel={deltaLabel(data.summary.week_over_week?.mention_rate_delta)?.label}
            />
            <StatMetric
              label="نسبة التوصية"
              value={pct(data.summary.recommendation_rate)}
              trend={deltaLabel(data.summary.week_over_week?.recommendation_rate_delta)?.trend}
              trendLabel={deltaLabel(data.summary.week_over_week?.recommendation_rate_delta)?.label}
            />
            <StatMetric
              label="ضمن أفضل 3 توصيات"
              value={pct(data.summary.top_3_rate)}
              trend={deltaLabel(data.summary.week_over_week?.top_3_rate_delta)?.trend}
              trendLabel={deltaLabel(data.summary.week_over_week?.top_3_rate_delta)?.label}
            />
            <StatMetric
              label="حصة الظهور مقابل المنافسين"
              value={pct(data.summary.share_of_voice)}
              trend={deltaLabel(data.summary.week_over_week?.share_of_voice_delta)?.trend}
              trendLabel={deltaLabel(data.summary.week_over_week?.share_of_voice_delta)?.label}
            />
            <StatMetric label="متوسط ترتيب التوصية" value={data.summary.avg_recommendation_rank !== null ? data.summary.avg_recommendation_rank.toFixed(1) : "—"} />
            <StatMetric label="نسبة الاستشهاد بمتجرك" value={pct(data.summary.citation_rate)} />
            <StatMetric
              label="أكثر منافس ظهورًا"
              value={data.summary.top_competitor ?? "—"}
              hint={data.summary.top_competitor ? `${data.summary.top_competitor_mentions} إشارة` : undefined}
            />
            <StatMetric label="عدد الإجابات المقاسة" value={String(data.summary.successful_answers)} />
          </section>

          {data.competitors.length > 0 && (
            <section>
              <h2 className="mb-3 text-base font-semibold text-text">المنافسون الأكثر ظهورًا معك</h2>
              <div className="flex flex-wrap gap-2">
                {data.competitors.map((c) => (
                  <Badge key={c.name} variant="neutral">{c.name} · {c.mentions}</Badge>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-3 text-base font-semibold text-text">الأسئلة والإجابات</h2>
            <div className="flex flex-col gap-3">
              {data.questions.map((q) => (
                <QuestionRow key={q.question_id} question={q} open={expanded.has(q.question_id)} onToggle={() => toggle(q.question_id)} />
              ))}
            </div>
          </section>

          {data.sources.length > 0 && (
            <section>
              <h2 className="mb-3 text-base font-semibold text-text">المصادر التي استشهدت بها الإجابات</h2>
              <Card padding="none">
                <div className="divide-y divide-border">
                  {data.sources.map((s) => (
                    <a
                      key={s.url}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-surface-hover"
                    >
                      <Badge variant={s.source_type === "official_store" ? "success" : s.source_type === "competitor_store" ? "warning" : "neutral"}>
                        {s.source_type}
                      </Badge>
                      <span className="flex-1 truncate text-text">{s.title || s.url}</span>
                      <span className="text-xs text-text-tertiary">×{s.count}</span>
                    </a>
                  ))}
                </div>
              </Card>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function QuestionRow({ question, open, onToggle }: { question: VisibilityQuestionItem; open: boolean; onToggle: () => void }) {
  return (
    <Card padding="none">
      <button onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-start">
        <Badge variant="neutral">{CATEGORY_LABELS[question.category] ?? question.category}</Badge>
        <span className="flex-1 text-sm font-medium text-text">{question.text}</span>
        <IconChevronDown className={`h-4 w-4 shrink-0 text-text-tertiary transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3">
          {question.answers.length === 0 ? (
            <NotMeasuredYet label="لم تُقَس هذه الإجابة بعد" />
          ) : (
            question.answers.map((a, i) => (
              <div key={i} className="flex flex-col gap-2 py-2">
                <div className="flex items-center gap-2">
                  <Badge variant="info">{a.engine}</Badge>
                  {a.status !== "success" ? (
                    <Badge variant="danger">تعذّر الحصول على إجابة</Badge>
                  ) : a.mention_type ? (
                    <Badge variant={MENTION_LABELS[a.mention_type]?.variant ?? "neutral"}>
                      {MENTION_LABELS[a.mention_type]?.label ?? a.mention_type}
                    </Badge>
                  ) : (
                    <NotMeasuredYet label="لم يُحلَّل بعد" />
                  )}
                </div>
                {a.raw_answer && <p className="text-sm leading-7 text-text-secondary">{a.raw_answer}</p>}
                {a.evidence_quote && (
                  <p className="border-e-2 border-primary/40 pe-3 text-xs italic text-text-tertiary">&quot;{a.evidence_quote}&quot;</p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </Card>
  );
}
