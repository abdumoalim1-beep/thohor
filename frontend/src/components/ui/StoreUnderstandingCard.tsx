"use client";
/* eslint-disable @next/next/no-img-element -- audited images come from arbitrary store domains */

import { useState } from "react";

import { StoreUnderstanding, postStoreFeedback } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { Card } from "./Card";
import { IconCheckCircle, IconExternal, IconStore } from "./icons";

export function StoreUnderstandingCard({ understanding, storeId, compact = false }: { understanding: StoreUnderstanding; storeId: string; compact?: boolean }) {
  const [confirmed, setConfirmed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [businessType, setBusinessType] = useState(understanding.business_type ?? "");
  const [categories, setCategories] = useState(understanding.category_previews.map((item) => item.name).join("، "));
  const [audience, setAudience] = useState(understanding.target_audience.join("، "));

  const saveCorrection = async () => {
    setSubmitting(true);
    try {
      await postStoreFeedback(storeId, "incorrect", ["profile_correction"], JSON.stringify({ business_type: businessType, categories, expected_audience: audience }));
      setEditing(false); setConfirmed(true);
    } finally { setSubmitting(false); }
  };
  const confirm = async () => {
    setSubmitting(true);
    try { await postStoreFeedback(storeId, "confirmed"); setConfirmed(true); }
    finally { setSubmitting(false); }
  };

  const productValue = understanding.product_count_status === "confirmed"
    ? String(understanding.products_found)
    : understanding.product_count_status === "estimated" && understanding.estimated_products_count !== null
      ? `نحو ${understanding.estimated_products_count}` : "غير متاح";

  return <Card padding="lg" className="overflow-hidden">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary-tint text-primary"><IconStore className="h-6 w-6" /></span>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-primary">فهمنا لمتجرك</p>
          <h2 className="truncate text-xl font-bold text-text">{understanding.display_name ?? "متجرك"}</h2>
          <a href={understanding.url} target="_blank" rel="noreferrer" dir="ltr" className="mt-0.5 inline-flex items-center gap-1 text-xs text-text-secondary hover:text-primary">{understanding.url.replace(/^https?:\/\//, "")}<IconExternal className="h-3 w-3" /></a>
        </div>
      </div>
      <Badge variant={understanding.understanding_stage === "ready" ? "success" : "neutral"}>{understanding.understanding_stage === "ready" ? "اكتمل التحليل الأساسي" : "التحليل الأساسي قيد الاكتمال"}</Badge>
    </header>

    <section className="mt-5 rounded-xl bg-primary-tint p-4">
      <p className="text-xs font-medium text-primary">نوع النشاط</p>
      <h3 className="mt-1 text-base font-semibold text-text">{understanding.business_type ?? "يحتاج تأكيدك"}</h3>
      {understanding.description && <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">{understanding.description}</p>}
    </section>

    <section className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <SummaryMetric label="نوع المتجر" value={understanding.business_type ?? "غير مؤكد"} />
      <SummaryMetric label="تصنيفات المنتجات" value={understanding.category_previews.length ? String(understanding.category_previews.length) : "غير متاح"} />
      <SummaryMetric label="حجم الكتالوج" value={productValue} />
      <SummaryMetric label="علامات يبيعها المتجر" value={understanding.sold_brands.length ? String(understanding.sold_brands.length) : "لم تُرصد"} />
    </section>

    {!compact && <>
      <section className="mt-7 border-t border-border pt-6">
        <div className="mb-3"><h3 className="font-semibold text-text">{understanding.category_previews.length} تصنيفات اكتشفها ظهور</h3><p className="mt-1 text-xs text-text-tertiary">نظرة على أقسام النشاط بدل عرض منتجات فردية عشوائية.{understanding.category_previews.some((item) => item.product_count === null) ? " تعذر تأكيد عدد المنتجات داخل بعض التصنيفات." : ""}</p></div>
        {understanding.category_previews.length ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {understanding.category_previews.map((category) => {
            const content = <><div className="aspect-[16/9] overflow-hidden bg-neutral-tint">{category.image_url ? <img src={category.image_url} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-text-tertiary"><IconStore className="h-6 w-6" /></div>}</div><div className="p-3"><div className="flex items-start justify-between gap-2"><h4 className="font-semibold text-text">{category.name}</h4><Badge variant={category.source === "catalog" ? "success" : "neutral"}>{category.source === "catalog" ? "صفحة موجودة" : category.source === "observed_products" ? "مستنتج من المنتجات" : "يحتاج تأكيدك"}</Badge></div>{category.product_count !== null && <p className="mt-1 text-xs text-text-secondary">{category.product_count} منتج</p>}</div></>;
            return category.url ? <a key={category.name} href={category.url} target="_blank" rel="noreferrer" className="overflow-hidden rounded-xl border border-border bg-bg-subtle hover:bg-surface-hover">{content}</a> : <div key={category.name} className="overflow-hidden rounded-xl border border-border bg-bg-subtle">{content}</div>;
          })}
        </div> : <p className="rounded-lg bg-bg-subtle p-4 text-sm text-text-secondary">لم نتأكد من تصنيفات مستقلة بعد. يمكنك إضافتها في قسم التأكيد أدناه.</p>}
      </section>

      <section className="mt-7 grid grid-cols-1 gap-4 border-t border-border pt-6 lg:grid-cols-2">
        <div><h3 className="font-semibold text-text">معلومات النشاط</h3>{understanding.business_info.length ? <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">{understanding.business_info.map((item) => <li key={item.kind}><a href={item.url} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded-lg border border-border p-3 text-sm font-medium text-text hover:bg-surface-hover">{item.label}<IconExternal className="h-3.5 w-3.5 text-text-tertiary" /></a></li>)}</ul> : <p className="mt-2 text-sm text-text-secondary">لم نرصد صفحات واضحة للشحن والدفع أو التواصل بعد.</p>}</div>
        <div><h3 className="font-semibold text-text">الجمهور المتوقع</h3>{understanding.target_audience.length ? <><div className="mt-3 flex flex-wrap gap-2">{understanding.target_audience.map((item) => <Badge key={item} variant="neutral">{item}</Badge>)}</div><p className="mt-2 text-xs leading-5 text-text-tertiary">{understanding.audience_basis}</p></> : <p className="mt-2 text-sm text-text-secondary">لم نحدد جمهورًا لعدم وجود دليل كافٍ.</p>}</div>
      </section>

      <section className="mt-7 rounded-xl border border-warning/20 bg-warning-tint p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold text-text">معلومات تحتاج تأكيدك</h3><p className="mt-1 text-sm text-text-secondary">أكد نوع النشاط والتصنيفات والجمهور المتوقع، أو عدّلها مباشرة.</p></div>{!editing && !confirmed && <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>تعديل البيانات</Button>}</div>
        {editing && <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3"><ProfileField label="نوع النشاط" value={businessType} onChange={setBusinessType} /><ProfileField label="التصنيفات" value={categories} onChange={setCategories} /><ProfileField label="الجمهور المتوقع" value={audience} onChange={setAudience} /></div>}
        <div className="mt-4 flex flex-wrap gap-2">{confirmed ? <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success"><IconCheckCircle className="h-4 w-4" /> تم حفظ تأكيدك</span> : editing ? <><Button size="sm" disabled={submitting} onClick={saveCorrection}>حفظ التعديلات والمتابعة</Button><Button size="sm" variant="ghost" onClick={() => setEditing(false)}>إلغاء</Button></> : <Button disabled={submitting} onClick={confirm}>تأكيد بيانات المتجر والمتابعة</Button>}</div>
      </section>

      <details className="mt-6 border-t border-border pt-4 text-sm"><summary className="cursor-pointer font-medium text-text-secondary">تفاصيل التحليل</summary><div className="mt-3 grid grid-cols-2 gap-2 text-xs text-text-tertiary sm:grid-cols-3"><span>صفحات تمت قراءتها: {understanding.pages_crawled}</span><span>منصة المتجر: تلقائية</span><span>{understanding.last_analyzed_at ? `آخر تحديث: ${relativeTime(understanding.last_analyzed_at)}` : "لم يكتمل التحديث"}</span></div></details>
    </>}
  </Card>;
}

function SummaryMetric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-border bg-bg-subtle p-3"><p className="text-xs text-text-tertiary">{label}</p><p className="mt-1 text-sm font-semibold leading-5 text-text">{value}</p></div>; }
function ProfileField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label className="text-xs font-medium text-text-secondary">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text outline-none focus:border-primary" /></label>; }
