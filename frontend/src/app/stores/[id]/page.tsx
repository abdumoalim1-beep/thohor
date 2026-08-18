"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { AIVisibilityListResponse, StoreDetail, getAIVisibility, getStore } from "@/lib/api";
import { appearanceLabel, appearanceOf, groupPromptObservations, sourceDomains, visibilityMetrics } from "@/lib/ai-product";

const analysisLinks = [
  ["فهم المتجر", "store", "هوية النشاط والتصنيفات والمعلومات المكتشفة"],
  ["صفحات الويب", "pages", "الصفحات التي قرأها ظهور وما وجده فيها"],
  ["الترتيب والظهور", "visibility", "ظهور المتجر في نتائج البحث المقاسة"],
  ["السوق وموضوعات البحث", "market", "الموضوعات والنوايا ومراحل قرار الشراء"],
  ["خريطة السوق", "competitors", "تمركز المتجر والبدائل المرصودة"],
  ["تفاصيل البحث", "research", "المهام وعمق البحث والأدلة"],
  ["التقرير الكامل", "reports", "الخلاصة الجامعة للتحليل"],
] as const;

export default function AIOverview() {
  const id = useParams<{ id: string }>().id;
  const [store, setStore] = useState<StoreDetail | null>(null);
  const [ai, setAI] = useState<AIVisibilityListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getStore(id), getAIVisibility(id)])
      .then(([storeData, aiData]) => { setStore(storeData); setAI(aiData); })
      .catch((reason) => setError(String(reason)));
  }, [id]);

  const derived = useMemo(() => ai ? {
    metrics: visibilityMetrics(ai.observations),
    prompts: groupPromptObservations(ai.observations),
    sources: sourceDomains(ai.observations),
  } : null, [ai]);

  if (error) return <ErrorState message={error} />;
  if (!store || !ai || !derived) return <LoadingState label="نقرأ نتائج تحليل المتجر..." />;

  const research = store.research_summary;
  const runStatus = store.latest_run?.status;
  const measuring = runStatus === "pending" || runStatus === "running";
  const { metrics, prompts, sources } = derived;

  return <div className="space-y-8 pb-16">
    <header>
      <Badge variant="primary">ذكاء التجارة والظهور</Badge>
      <h1 className="mt-3 text-3xl font-semibold text-text">ماذا عرف ظهور، وأين يظهر متجرك؟</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
        نفصل بين تحليل المتجر والويب المكتمل، وبين قياسات الظهور التي تحتاج تشغيلًا حيًا. عدم وجود قياس ظهور لا يعني أن بقية التحليل مفقودة.
      </p>
    </header>

    <Card className="border-primary/20 bg-primary-tint" padding="lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">ما اكتمل فعليًا</h2>
          <p className="mt-1 text-sm text-text-secondary">نتائج موثقة من أحدث تحليل مكتمل للمتجر.</p>
        </div>
        {measuring && <Badge variant="primary">يجري تحديث قياسات الظهور الآن</Badge>}
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Fact value={research?.pages_crawled ?? store.pages_crawled} label="صفحة قُرئت" />
        <Fact value={research?.intents_discovered ?? store.intents_found} label="موضوع بحث مكتشف" />
        <Fact value={research?.search_queries_executed ?? 0} label="عملية بحث منفذة" />
        <Fact value={research?.ai_conversations_executed ?? 0} label="محادثة تحليلية" />
        <Fact value={research?.evidence_records ?? 0} label="سجل دليل" />
      </div>
    </Card>

    <section>
      <div className="mb-4">
        <h2 className="text-xl font-semibold">كل مساحات التحليل</h2>
        <p className="mt-1 text-sm text-text-secondary">لم تُحذف التحليلات السابقة؛ هذه روابطها المباشرة.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {analysisLinks.map(([title, path, description]) => <Link key={path} href={`/stores/${id}/${path}`}>
          <Card className="h-full transition hover:border-primary/40 hover:shadow-sm">
            <h3 className="font-semibold text-text">{title}</h3>
            <p className="mt-2 text-sm leading-6 text-text-secondary">{description}</p>
          </Card>
        </Link>)}
      </div>
    </section>

    <section>
      <div className="mb-4">
        <h2 className="text-xl font-semibold">الظهور داخل إجابات الذكاء الاصطناعي</h2>
        <p className="mt-1 text-sm text-text-secondary">هذه المقاييس مبنية فقط على الإجابات التي جرى التقاطها، وليست تقديرًا أو بيانات مختلقة.</p>
      </div>
      <div className="grid overflow-hidden rounded-2xl border border-border bg-white md:grid-cols-3">
        <Metric title="معدل ذكر المتجر" value={metrics.validAnswers ? `${metrics.mentionRate}%` : "لم يُقَس بعد"} note={metrics.validAnswers ? `من ${metrics.validAnswers} إجابة صالحة` : measuring ? "القياس الحي قيد التنفيذ" : "لا توجد إجابات ملتقطة بعد"} />
        <Metric title="معدل التوصية" value="غير مصنف" note="الذكر لا يُعامل كتوصية دون دليل صريح من نص الإجابة" />
        <Metric title="معدل الاستشهاد" value={metrics.citationRate === null ? "غير متاح" : `${metrics.citationRate}%`} note={metrics.citationRate === null ? "لم تعرض الإجابات مصادر قابلة للرصد بعد" : `من ${metrics.citationCapableAnswers} إجابة تعرض مصادر`} />
      </div>
      <p className="mt-3 rounded-xl bg-bg-subtle px-4 py-3 text-xs text-text-secondary">
        العينة الحالية: {metrics.validAnswers} إجابة · {metrics.prompts} سؤال · {metrics.surfaces} محركات. النسب تصف العينة المرصودة ولا تمثل مشترين أو مبيعات.
      </p>
    </section>

    <div className="grid gap-5 xl:grid-cols-[1.35fr_.75fr]">
      <Card padding="lg">
        <div className="flex items-center justify-between gap-4">
          <div><h2 className="text-lg font-semibold">الظهور حسب سؤال الشراء</h2><p className="text-xs text-text-tertiary">معدل الذكر عبر التشغيلات الفعلية لكل سؤال</p></div>
          <Link href={`/stores/${id}/prompts`} className="text-sm font-semibold text-primary">كل الأسئلة</Link>
        </div>
        <div className="mt-6 space-y-5">{prompts.slice(0, 7).map((row) => <div key={row.prompt}>
          <div className="mb-2 flex justify-between gap-3 text-sm"><span className="line-clamp-1 font-medium">{row.prompt}</span><span className="font-bold text-primary">{row.mentionRate}%</span></div>
          <div className="h-2 overflow-hidden rounded-full bg-neutral-tint"><div className="h-full rounded-full bg-primary" style={{ width: `${row.mentionRate}%` }} /></div>
          <p className="mt-1 text-[11px] text-text-tertiary">{row.observations.length} إجابات</p>
        </div>)}{!prompts.length && <NoData text={measuring ? "نجمع الإجابات الحية الآن..." : "لا توجد إجابات مرصودة كافية بعد."} />}</div>
      </Card>
      <Card padding="lg">
        <h2 className="text-lg font-semibold">أكثر المصادر حضورًا</h2>
        <div className="mt-5 space-y-4">{sources.slice(0, 7).map((row, index) => <div key={row.domain} className="flex items-center justify-between border-b border-border pb-3"><span className="text-sm"><b className="me-2 text-text-tertiary">{index + 1}</b>{row.domain}</span><span className="text-sm font-bold">{row.count}</span></div>)}{!sources.length && <NoData text="لم تظهر مصادر قابلة للرصد بعد." />}</div>
        <Link href={`/stores/${id}/citations`} className="mt-5 inline-block text-sm font-semibold text-primary">خريطة المصادر</Link>
      </Card>
    </div>

    {!!ai.observations.length && <section>
      <div className="mb-3 flex items-end justify-between"><div><h2 className="text-lg font-semibold">أحدث الإجابات</h2><p className="text-xs text-text-tertiary">الدليل الفعلي خلف المقاييس</p></div><Link href={`/stores/${id}/responses`} className="text-sm font-semibold text-primary">عرض الكل</Link></div>
      <div className="grid gap-4 md:grid-cols-2">{ai.observations.slice(0, 4).map((observation) => <Link key={observation.id} href={`/stores/${id}/responses?answer=${observation.id}`}><Card className="h-full transition hover:border-primary/30"><div className="flex items-center justify-between"><Badge variant="neutral">{observation.surface}</Badge><span className="text-xs text-text-tertiary">تشغيل {observation.repetition_index + 1}</span></div><h3 className="mt-3 line-clamp-2 font-semibold">{observation.prompt_text}</h3><p className="mt-2 line-clamp-3 text-sm leading-6 text-text-secondary">{observation.response_text || "نص الإجابة غير متاح لهذا الرصد."}</p><p className="mt-4 text-xs font-medium text-primary">{appearanceLabel(appearanceOf(observation))}</p></Card></Link>)}</div>
    </section>}
  </div>;
}

function Fact({ value, label }: { value: number; label: string }) { return <div className="rounded-xl border border-primary/10 bg-white p-4"><p className="text-2xl font-bold text-primary">{value.toLocaleString("ar-SA")}</p><p className="mt-1 text-xs text-text-secondary">{label}</p></div>; }
function Metric({ title, value, note }: { title: string; value: string; note: string }) { return <div className="border-b border-border p-6 last:border-0 md:border-b-0 md:border-e"><p className="text-sm text-text-secondary">{title}</p><p className="mt-2 text-2xl font-bold text-text">{value}</p><p className="mt-2 text-xs leading-5 text-text-tertiary">{note}</p></div>; }
function NoData({ text }: { text: string }) { return <p className="rounded-xl bg-bg-subtle p-4 text-sm text-text-tertiary">{text}</p>; }
