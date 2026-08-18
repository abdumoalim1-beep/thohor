"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import {
  ImplementationPackage,
  RecommendationDetail,
  RecommendationEvidenceResponse,
  getImplementationPackage,
  getRecommendation,
  getRecommendationEvidence,
  patchRecommendationStatus,
} from "@/lib/api";

export default function RecommendationDetailPage() {
  const { recId } = useParams<{ id: string; recId: string }>();
  const [rec, setRec] = useState<RecommendationDetail | null>(null);
  const [evidence, setEvidence] = useState<RecommendationEvidenceResponse | null>(null);
  const [pkg, setPkg] = useState<ImplementationPackage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getRecommendation(recId), getRecommendationEvidence(recId), getImplementationPackage(recId)])
      .then(([recommendation, evidenceResult, packageResult]) => {
        setRec(recommendation);
        setEvidence(evidenceResult);
        setPkg(packageResult.implementation_package);
      })
      .catch((reason) => setError(String(reason)));
  }, [recId]);

  if (error) return <ErrorState message={error} />;
  if (!rec) return <LoadingState />;

  const updateStatus = async (status: string) => {
    try { setRec(await patchRecommendationStatus(recId, status)); }
    catch (reason) { setError(String(reason)); }
  };

  const evidenceLines = [
    ...(evidence?.findings.map((item) => item.statement) ?? []),
    ...(evidence?.evidence.map((item) => item.summary).filter((item): item is string => Boolean(item)) ?? []),
  ];

  return (
    <div className="space-y-8 pb-16">
      <header>
        <Badge variant="primary">إجراء مبني على فجوة مرصودة</Badge>
        <h1 className="mt-3 text-3xl font-semibold text-text">{rec.title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">هذه ليست علة قطعية لغياب المنتج؛ إنها فجوة قابلة للإصلاح قد تقلل فرصة التوصية.</p>
      </header>

      <section className="grid gap-4 lg:grid-cols-5">
        <Step number="1" title="الاستنتاج" text={rec.what_we_found || "رُصدت فجوة تحتاج معالجة."} />
        <Step number="2" title="الدليل" text={evidenceLines[0] || "لا يوجد مقتطف تفصيلي إضافي محفوظ."} />
        <Step number="3" title="لماذا يهم" text={rec.why_it_matters} />
        <Step number="4" title="الإجراء" text={rec.what_to_do} />
        <Step number="5" title="التنفيذ" text={rec.implementation_steps[0] || "راجع الحزمة الجاهزة أدناه."} />
      </section>

      <Card className="border-primary/20 bg-primary-tint">
        <h2 className="font-semibold text-text">حدود هذا الاستنتاج</h2>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          بعد التنفيذ لا نثبت التحسن بإعادة واحدة. نكرر السؤال ونقارن معدل الذكر، معدل التوصية، معدل الاستشهاد، وثبات المعلومات عبر الزمن والمحركات المتاحة.
        </p>
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-text">حزمة التنفيذ</h2>
        {pkg ? <Package packageData={pkg} /> : <Card><p className="text-sm text-text-tertiary">لا توجد حزمة تنفيذ جاهزة لهذه الفجوة بعد.</p></Card>}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-text">خطوات التنفيذ</h2>
        <ol className="space-y-2">
          {rec.implementation_steps.map((step, index) => (
            <li key={`${index}-${step}`} className="flex gap-3 rounded-xl border border-border bg-white p-4 text-sm leading-6 text-text-secondary">
              <span className="font-bold text-primary">{index + 1}</span><span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="neutral">{statusLabel(rec.status)}</Badge>
          {rec.status === "new" && <Button size="sm" onClick={() => updateStatus("planned")}>جاهزة للمراجعة</Button>}
          {rec.status === "planned" && <Button size="sm" onClick={() => updateStatus("in_progress")}>اعتماد وبدء التنفيذ</Button>}
          {rec.status === "in_progress" && <Button size="sm" onClick={() => updateStatus("implemented")}>تم التنفيذ</Button>}
        </div>
        <p className="mt-3 text-xs text-text-tertiary">الاعتماد يدير سير العمل فقط. النشر المباشر داخل منصة المتجر مؤجل لحين الربط.</p>
      </Card>
    </div>
  );
}

function Step({ number, title, text }: { number: string; title: string; text: string }) {
  return <Card className="lg:col-span-1"><span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">{number}</span><h2 className="mt-3 font-semibold text-text">{title}</h2><p className="mt-2 text-sm leading-6 text-text-secondary">{text}</p></Card>;
}

function Package({ packageData }: { packageData: ImplementationPackage }) {
  const blocks: Array<[string, string | string[] | undefined]> = [
    ["العنوان", packageData.suggested_title],
    ["Meta description", packageData.suggested_meta_description],
    ["H1", packageData.h1],
    ["H2", packageData.suggested_h2_sections],
    ["FAQ", packageData.faq_questions],
    ["الروابط الداخلية", packageData.internal_links],
    ["النص المقترح", packageData.suggested_copy],
    ["تعليمات المطور", packageData.developer_instructions],
    ["تعليمات كاتب المحتوى", packageData.content_writer_instructions],
  ];
  return <div className="grid gap-3 md:grid-cols-2">{blocks.filter(([, value]) => Array.isArray(value) ? value.length : Boolean(value)).map(([label, value]) => <Card key={label}><p className="text-xs font-semibold text-primary">{label}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-text-secondary">{Array.isArray(value) ? value.join("\n") : value}</p></Card>)}</div>;
}

function statusLabel(status: string) {
  return ({ new: "جديد", planned: "جاهز للمراجعة", in_progress: "قيد التنفيذ", implemented: "تم التنفيذ", monitoring: "قيد القياس" } as Record<string, string>)[status] ?? status;
}
