"use client";
/* eslint-disable @next/next/no-img-element -- screenshot is a signed artifact URL */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { IconArrowLeft, IconCheckCircle, IconExternal } from "@/components/ui/icons";
import { capturePageScreenshot, getPageDetail, PageScreenshotResult, PageWorkspaceDetail } from "@/lib/api";

export default function PageStudio() {
  const { id: storeId, pageId } = useParams<{ id: string; pageId: string }>();
  const [page, setPage] = useState<PageWorkspaceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [screenshot, setScreenshot] = useState<PageScreenshotResult | null>(null);
  const [capturing, setCapturing] = useState(false);
  useEffect(() => { getPageDetail(storeId, pageId).then(setPage).catch((reason) => setError(String(reason))); }, [storeId, pageId]);
  const capture = async (mobile = false) => {
    setCapturing(true); setError(null);
    try { setScreenshot(await capturePageScreenshot(storeId, pageId, mobile)); }
    catch (reason) { setError(String(reason)); }
    finally { setCapturing(false); }
  };
  if (error) return <ErrorState message={error} />;
  if (!page) return <LoadingState label="نفتح استوديو الصفحة..." />;
  return <div className="flex flex-col gap-6">
    <header><Link href={`/stores/${storeId}/pages`} className="inline-flex items-center gap-1 text-sm text-text-secondary"><IconArrowLeft className="h-4 w-4 rotate-180" />كل الصفحات</Link><div className="mt-3 flex flex-wrap items-start justify-between gap-4"><div><Badge variant="neutral">{page.page_type}</Badge><h1 className="mt-2 text-2xl font-bold text-text">{page.h1 || page.title || "صفحة بلا عنوان مرصود"}</h1><a href={page.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-primary"><IconExternal className="h-4 w-4" />فتح الصفحة الأصلية</a></div><p className="text-2xl font-bold text-primary">{page.completion_score}%</p></div></header>
    <section className="grid gap-6 xl:grid-cols-[1.4fr_.8fr]">
      <Card padding="none" className="overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3"><span className="text-xs font-semibold text-text-secondary">الصفحة الحالية</span><div className="flex gap-2"><button disabled={capturing} onClick={() => capture(false)} className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">لقطة سطح المكتب</button><button disabled={capturing} onClick={() => capture(true)} className="rounded-lg border border-primary px-3 py-2 text-xs font-semibold text-primary disabled:opacity-50">لقطة الجوال</button></div></div>{screenshot ? <div className="relative"><img src={screenshot.screenshot_url} alt="لقطة حقيقية للصفحة" className="h-auto w-full" />{screenshot.annotations.map((annotation,index)=><span key={`${annotation.key}-${index}`} title={annotation.key} className="absolute flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-primary text-xs font-bold text-white shadow" style={{left:`${annotation.x/screenshot.width*100}%`,top:`${annotation.y/screenshot.height*100}%`}}>{index+1}</span>)}</div> : <iframe src={page.url} title={page.title || page.url} className="h-[45rem] w-full bg-white" sandbox="allow-same-origin allow-scripts" />}</Card>
      <aside className="space-y-4"><Card padding="lg"><h2 className="font-bold text-text">تشخيص الصفحة</h2><div className="mt-4 space-y-3">{page.checks.map((check) => <div key={check.key} className="rounded-xl border border-border p-3"><div className="flex gap-2"><IconCheckCircle className={`h-4 w-4 ${check.status === "present" ? "text-success" : "text-warning"}`} /><div><p className="text-sm font-semibold text-text">{check.label}</p><p className="mt-1 text-xs leading-5 text-text-secondary">{check.message}</p></div></div></div>)}</div></Card><Card padding="lg"><h2 className="font-bold text-text">التوصيات المرتبطة</h2>{page.recommendations.length ? <div className="mt-3 space-y-2">{page.recommendations.map((recommendation) => <Link key={recommendation.id} href={`/stores/${storeId}/recommendations/${recommendation.id}`} className="block rounded-xl border border-border p-3 text-sm font-semibold text-primary">{recommendation.title}</Link>)}</div> : <p className="mt-3 text-sm leading-6 text-text-secondary">لا توجد توصية مدعومة مرتبطة بهذه الصفحة بعد.</p>}</Card></aside>
    </section>
  </div>;
}
