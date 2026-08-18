"use client";

import Link from "next/link";
import { relativeTime } from "@/lib/format";
import { IconBell, IconLoader } from "./icons";

export function Topbar({storeUrl,lastUpdatedAt,unreadCount,storeId,onMenuClick,progress}:{storeUrl?:string;lastUpdatedAt?:string|null;unreadCount?:number;storeId:string;onMenuClick?:()=>void;progress?:{completedSteps:number;totalSteps:number}|null}) {
  return <div className="shrink-0">
    <div className="fixed inset-x-0 top-0 z-[60] flex min-h-9 items-center justify-center gap-2 bg-gradient-to-l from-[#4f46e5] via-[#6366f1] to-[#38bdf8] px-4 py-2 text-center text-xs font-semibold text-white">{progress?<><IconLoader className="h-3.5 w-3.5 animate-spin"/>التحليل الموسع مستمر في الخلفية — اكتمل {progress.completedSteps} من {progress.totalSteps}</>:<>اكتمل التحليل الأساسي · تُحدّث القياسات تلقائيًا عند توفر نتائج جديدة</>}</div>
    <header className="flex h-16 items-center justify-between border-b border-border bg-white/95 px-4 backdrop-blur sm:px-7">
      <div className="flex items-center gap-3"><button type="button" onClick={onMenuClick} className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-text-secondary md:hidden" aria-label="القائمة"><span className="text-xl">☰</span></button>{storeUrl&&<div><p dir="ltr" className="max-w-[260px] truncate text-left text-sm font-medium text-text">{storeUrl.replace(/^https?:\/\//,"")}</p><p className="text-xs text-text-tertiary">آخر تحديث: {relativeTime(lastUpdatedAt??null)}</p></div>}</div>
      <div className="flex items-center gap-3"><span className="hidden rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-text-secondary sm:block">بيانات حقيقية من آخر رصد</span><Link href={`/stores/${storeId}/alerts`} className="relative flex h-10 w-10 items-center justify-center rounded-full border border-border bg-surface text-text-secondary hover:text-text" aria-label="التنبيهات"><IconBell className="h-5 w-5"/>{!!unreadCount&&unreadCount>0&&<span className="absolute -end-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{unreadCount>9?"9+":unreadCount}</span>}</Link></div>
    </header>
  </div>;
}
