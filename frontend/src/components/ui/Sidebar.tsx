"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "./BrandMark";
import {
  IconCompetitors, IconEye, IconInfoCircle, IconMarket, IconOpportunity,
  IconOverview, IconRecommendations, IconReports, IconSearch, IconSettings,
  IconSpark, IconStore,
} from "./icons";

type Item = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

const AI_JOURNEY: Item[] = [
  { href: "", label: "النظرة العامة", icon: IconOverview },
  { href: "/prompts", label: "أسئلة الشراء", icon: IconInfoCircle },
  { href: "/responses", label: "إجابات AI", icon: IconEye },
  { href: "/ai-answers", label: "ظهورك في إجابات AI (تجريبي)", icon: IconSpark },
  { href: "/citations", label: "المصادر والاستشهادات", icon: IconReports },
  { href: "/opportunities", label: "فرص التوصية", icon: IconOpportunity },
  { href: "/actions", label: "الإجراءات", icon: IconRecommendations },
];

const ANALYSIS: Item[] = [
  { href: "/store", label: "فهم المتجر", icon: IconStore },
  { href: "/pages", label: "صفحات الويب", icon: IconReports },
  { href: "/visibility", label: "الترتيب والظهور", icon: IconEye },
  { href: "/market", label: "السوق وموضوعات البحث", icon: IconMarket },
  { href: "/competitors", label: "خريطة السوق", icon: IconCompetitors },
  { href: "/research", label: "تفاصيل البحث", icon: IconSearch },
  { href: "/reports", label: "التقرير الكامل", icon: IconReports },
];

export function Sidebar({ storeId }: { storeId: string }) {
  const pathname = usePathname();
  const base = `/stores/${storeId}`;
  return <aside className="flex h-full w-[17.5rem] shrink-0 flex-col border-e border-border bg-white">
    <div className="flex items-center gap-3 border-b border-border px-6 py-6"><BrandMark className="h-10 w-10"/><div><p className="text-xl font-bold text-text">ظهور</p><p className="text-[10px] tracking-[.14em] text-primary">AI COMMERCE INTELLIGENCE</p></div></div>
    <nav className="flex flex-1 flex-col overflow-y-auto px-4 py-5">
      <NavGroup title="من السؤال إلى الإجراء" items={AI_JOURNEY} base={base} pathname={pathname}/>
      <NavGroup title="تحليل المتجر والويب" items={ANALYSIS} base={base} pathname={pathname} className="mt-7"/>
    </nav>
    <div className="border-t border-border p-4"><Link href={`${base}/settings`} className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm text-text-secondary hover:bg-surface-hover"><IconSettings className="h-5 w-5"/>الإعدادات</Link></div>
  </aside>;
}

function NavGroup({ title, items, base, pathname, className = "" }: { title: string; items: Item[]; base: string; pathname: string; className?: string }) {
  return <section className={className}><p className="mb-2 px-4 text-[11px] font-semibold text-text-tertiary">{title}</p><div className="space-y-1">{items.map((item) => { const href = base + item.href; const active = item.href === "" ? pathname === href : pathname.startsWith(href); const Icon = item.icon; return <Link key={item.href} href={href} className={`flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition ${active ? "bg-primary text-white" : "text-text-secondary hover:bg-primary-tint hover:text-primary"}`}><Icon className="h-5 w-5"/>{item.label}</Link>; })}</div></section>;
}
