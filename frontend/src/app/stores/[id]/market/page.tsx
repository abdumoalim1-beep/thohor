"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { IconExternal, IconMarket } from "@/components/ui/icons";
import { AIVisibilityListResponse, IntentListItem, OpportunityItem, getAIVisibility, getIntents, getOpportunities } from "@/lib/api";
import { VISIBILITY_LABELS, VisibilityState, groupSimilarSearches, isUsefulProductSearch, rankValue, visibilityCounts, visibilityState } from "@/lib/search-visibility";

const FILTERS: Array<{ key: "all" | VisibilityState | "opportunity"; label: string }> = [
  { key: "all", label: "الكل" }, { key: "top10", label: "ظهر" }, { key: "not_seen", label: "لم يظهر" },
  { key: "opportunity", label: "فرصة مرتفعة" },
];

export default function SearchVisibilityPage() {
  const storeId = useParams<{ id: string }>().id;
  const [intents, setIntents] = useState<IntentListItem[] | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [category, setCategory] = useState("all");
  const [selected, setSelected] = useState<IntentListItem | null>(null);
  const [tab, setTab] = useState<"google" | "ai">(() => typeof window !== "undefined" && window.location.search.includes("tab=ai") ? "ai" : "google");
  const [aiVisibility, setAiVisibility] = useState<AIVisibilityListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { let active = true; Promise.all([getIntents(storeId), getOpportunities(storeId), getAIVisibility(storeId)]).then(([i, o, ai]) => { if (active) { setIntents(groupSimilarSearches(i.intents.filter(isUsefulProductSearch))); setOpportunities(o.opportunities); setAiVisibility(ai); } }).catch((e) => active && setError(String(e))); return () => { active = false; }; }, [storeId]);
  const opportunityIds = useMemo(() => new Set(opportunities.flatMap((item) => item.affected_intents)), [opportunities]);
  if (error) return <ErrorState message={error} />;
  if (!intents) return <LoadingState />;
  if (tab === "ai") return <div className="flex flex-col gap-8 pb-12"><PageHeader tab={tab} onTab={setTab}/><AIVisibilityPanel data={aiVisibility}/></div>;
  if (!intents.length) return <EmptyState icon={<IconMarket className="h-5 w-5" />} title="لا توجد عمليات بحث مختبرة بعد" />;

  const counts = visibilityCounts(intents);
  const appeared = counts.top3 + counts.top10 + counts.top20;
  const measuredCount = intents.length - counts.insufficient - counts.failed;
  const ranked = [...intents].filter((item) => item.client_rank !== null).sort((a, b) => rankValue(a) - rankValue(b));
  const strongest = ranked[0] ?? null;
  const gaps = intents.filter((item) => ["not_seen", "top20"].includes(visibilityState(item)) && (opportunityIds.has(item.id) || item.commercial_stage === "purchase")).slice(0, 3);
  const categories = [...new Set(intents.map((item) => item.category).filter(Boolean))] as string[];
  const filtered = intents.filter((item) => (category === "all" || item.category === category) && (filter === "all" || (filter === "opportunity" ? opportunityIds.has(item.id) : filter === "top10" ? ["top3", "top10"].includes(visibilityState(item)) : visibilityState(item) === filter)));

  return <div className="flex flex-col gap-8 pb-12">
    <PageHeader tab={tab} onTab={setTab}/>

    <Card padding="lg" className="border-primary/20 bg-primary-tint">
      <p className="text-sm font-medium text-primary">نتيجة مرصودة</p><p className="mt-1 text-3xl font-bold text-text">ظهر متجرك في {appeared} من {measuredCount} عملية بحث مكتملة</p>
      {measuredCount < intents.length && <p className="mt-2 text-xs text-warning">خُطط لـ{intents.length} عملية؛ تعذر {counts.failed} وبقي {counts.insufficient} لم يبدأ قياسها.</p>}
      <p className="mt-2 text-sm text-text-secondary">{strongest ? `أقوى ظهور: «${strongest.topic}» في المركز ${strongest.client_rank}.` : "لم نرصد ظهورًا مؤكدًا بعد."} {gaps[0] ? `أكبر فجوة مرتبطة بمنتجاتك: «${gaps[0].topic}».` : counts.failed ? `لا نحدد فجوة نهائية قبل إعادة ${counts.failed} اختبارات متعذرة.` : "لا توجد فجوة موثقة كافية للعرض."}</p>
    </Card>

    <section><h2 className="mb-3 font-semibold text-text">توزيع الظهور</h2><Card padding="md"><div className="flex h-4 overflow-hidden rounded-full bg-neutral-tint">{(["top3","top10","top20","not_seen","failed","insufficient"] as VisibilityState[]).map((state) => counts[state] ? <div key={state} title={`${VISIBILITY_LABELS[state]}: ${counts[state]}`} className={{top3:"bg-success",top10:"bg-primary",top20:"bg-warning",not_seen:"bg-danger",failed:"bg-warning",insufficient:"bg-border-strong"}[state]} style={{width:`${counts[state] / intents.length * 100}%`}} /> : null)}</div><div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-6">{(["top3","top10","top20","not_seen","failed","insufficient"] as VisibilityState[]).map((state) => <div key={state}><p className="text-lg font-bold text-text">{counts[state]}</p><p className="text-xs text-text-secondary">{VISIBILITY_LABELS[state]}</p></div>)}</div></Card></section>

    <section><div className="mb-3 flex flex-wrap items-end justify-between gap-3"><div><h2 className="font-semibold text-text">خريطة عمليات البحث</h2><p className="mt-1 text-xs text-text-tertiary">كل نقطة هي أفضل مركز رصدناه وقت الفحص.</p></div><div className="flex flex-wrap gap-2">{FILTERS.map((item) => <Button key={item.key} size="sm" variant={filter === item.key ? "primary" : "secondary"} onClick={() => setFilter(item.key)}>{item.label}</Button>)}<select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-md border border-border bg-surface px-2 text-sm"><option value="all">كل التصنيفات</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></div></div>
      <Card padding="none" className="overflow-hidden"><ul className="divide-y divide-border">{filtered.map((intent) => { const state = visibilityState(intent); const rank = intent.client_rank; return <li key={intent.id}><button onClick={() => setSelected(intent)} className="grid w-full grid-cols-1 gap-2 px-4 py-3 text-right hover:bg-surface-hover md:grid-cols-[minmax(0,1.6fr)_1fr_2fr_1fr] md:items-center"><span><strong className="block text-sm text-text">{intent.topic}</strong><span className="text-xs text-text-tertiary">{intent.category ?? "غير مصنف"}</span></span><Badge variant={state === "top3" || state === "top10" ? "success" : state === "insufficient" ? "neutral" : "warning"}>{VISIBILITY_LABELS[state]}</Badge><span className="relative block h-2 rounded-full bg-neutral-tint">{rank && rank <= 20 ? <span className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full bg-primary" style={{right:`${Math.max(0,(20-rank)/19*100)}%`}} /> : null}</span><span className="text-sm font-medium text-text">{rank && rank <= 20 ? `المركز ${rank}` : VISIBILITY_LABELS[state]}</span></button></li>; })}</ul></Card>
    </section>

    <div className="grid gap-5 lg:grid-cols-2"><TopList title="أقوى الظهور" items={ranked.slice(0,3)} onSelect={setSelected} /><section><h2 className="mb-3 font-semibold text-text">أكبر فجوات الظهور</h2><div className="space-y-2">{gaps.map((item) => <Card key={item.id} padding="md"><h3 className="font-semibold text-text">{item.topic}</h3><p className="mt-1 text-sm text-text-secondary">اختبرنا هذه العملية ولم نرصد ظهورًا قويًا، وهي مرتبطة بفرصة موجودة في متجرك.</p><Link href={`/stores/${storeId}/recommendations`} className="mt-3 inline-block text-sm font-medium text-primary">عرض الفرصة</Link></Card>)}{!gaps.length && <p className="text-sm text-text-tertiary">بيانات غير كافية لتحديد فجوات مرتبطة بمنتجات المتجر.</p>}</div></section></div>

    {selected && <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 md:items-center" onClick={() => setSelected(null)}><Card padding="lg" className="w-full max-w-xl" ><div onClick={(e) => e.stopPropagation()}><div className="flex items-start justify-between gap-4"><div><p className="text-xs text-primary">تفاصيل عملية البحث</p><h2 className="mt-1 text-lg font-bold text-text">{selected.topic}</h2></div><Button variant="ghost" size="sm" onClick={() => setSelected(null)}>إغلاق</Button></div><dl className="mt-5 grid grid-cols-2 gap-4 text-sm"><Detail label="محرك البحث" value={selected.search_engine??"Google"}/><Detail label="حالة الظهور" value={VISIBILITY_LABELS[visibilityState(selected)]}/><Detail label="أفضل مركز" value={selected.client_rank?String(selected.client_rank):selected.search_status==="measured"?"لم يظهر":"تعذر القياس"}/><Detail label="نطاق الفحص" value={selected.search_results_count?`أول ${selected.search_results_count} نتيجة`:"غير محفوظ"}/><Detail label="الدولة" value={selected.search_country??"غير محفوظ"}/><Detail label="الجهاز" value={selected.search_device??"غير محفوظ"}/><Detail label="وقت الرصد" value={selected.search_observed_at?new Date(selected.search_observed_at).toLocaleString("ar-SA"):"غير محفوظ"}/></dl>{selected.client_url && <a href={selected.client_url} target="_blank" rel="noreferrer" className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-primary">فتح صفحة المتجر التي ظهرت <IconExternal className="h-4 w-4"/></a>}<p className="mt-5 text-xs leading-5 text-text-tertiary">المركز مرصود وقت الفحص وقد يختلف حسب الموقع والوقت والمستخدم.</p></div></Card></div>}
  </div>;
}

function TopList({title,items,onSelect}:{title:string;items:IntentListItem[];onSelect:(item:IntentListItem)=>void}) { return <section><h2 className="mb-3 font-semibold text-text">{title}</h2><div className="space-y-2">{items.map((item) => <button key={item.id} onClick={() => onSelect(item)} className="flex w-full items-center justify-between rounded-xl border border-border bg-surface p-4 text-right hover:bg-surface-hover"><span><strong className="block text-sm text-text">{item.topic}</strong><span className="text-xs text-text-tertiary">{item.client_url ? "صفحة ظهور محفوظة" : "لا توجد صفحة محفوظة"}</span></span><span className="text-xl font-bold text-primary">#{item.client_rank}</span></button>)}</div></section>; }
function Detail({label,value}:{label:string;value:string}) { return <div><dt className="text-xs text-text-tertiary">{label}</dt><dd className="mt-1 font-medium text-text">{value}</dd></div>; }
function PageHeader({tab,onTab}:{tab:"google"|"ai";onTab:(tab:"google"|"ai")=>void}){return <header><h1 className="text-xl font-bold text-text">ظهورك في البحث</h1><p className="mt-1 text-sm text-text-secondary">نفصل ترتيب Google عن ذكر المتجر داخل إجابات الذكاء الاصطناعي.</p><div className="mt-4 flex gap-2"><Button variant={tab==="google"?"primary":"secondary"} onClick={()=>onTab("google")}>Google</Button><Button variant={tab==="ai"?"primary":"secondary"} onClick={()=>onTab("ai")}>إجابات الذكاء الاصطناعي</Button></div></header>}
function AIVisibilityPanel({data}:{data:AIVisibilityListResponse|null}) {
  if (!data) return <LoadingState />;
  const grouped = new Map<string, typeof data.observations>();
  for (const item of data.observations) grouped.set(item.prompt_text, [...(grouped.get(item.prompt_text) ?? []), item]);
  const questions = [...grouped.entries()].map(([prompt, observations]) => ({
    prompt,
    observations,
    mentioned: observations.some((item) => item.mentioned),
    cited: observations.some((item) => item.citations.length > 0),
    surfaces: [...new Set(observations.map((item) => item.surface))],
    competitors: [...new Set(observations.flatMap((item) => item.competitors_mentioned))],
  }));
  const mentioned = questions.filter((item) => item.mentioned).length;
  const cited = questions.filter((item) => item.cited).length;
  return <><Card padding="lg" className="border-primary/20 bg-primary-tint"><p className="text-sm font-medium text-primary">نتيجة إجابات الذكاء الاصطناعي</p><p className="mt-1 text-3xl font-bold text-text">{questions.length?`ذُكر متجرك في ${mentioned} من أصل ${questions.length} سؤالًا اختبرناه`:"لم يكتمل أي اختبار بعد"}</p><p className="mt-2 text-sm text-text-secondary">{questions.length?`ووجدنا استشهادًا برابط المتجر في ${cited} من الأسئلة. أعدنا بعض الاختبارات عبر أكثر من محرك للتحقق.`:"لا نعرض غياب القياس كصفر."}</p></Card>{data.unavailable_surfaces.length>0&&<p className="text-xs text-warning">محركات غير مفعلة ولم تُحتسب: {data.unavailable_surfaces.join("، ")}</p>}<section><h2 className="mb-3 font-semibold text-text">الأسئلة التي اختبرناها</h2><div className="space-y-2">{questions.slice(0,12).map(item=><Card key={item.prompt} padding="sm"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-medium text-text">{item.prompt}</h3><p className="mt-1 text-xs text-text-tertiary">{item.surfaces.join("، ")} · اختُبر {item.observations.length} {item.observations.length === 1 ? "مرة" : "مرات"}</p></div><Badge variant={item.mentioned?"success":"neutral"}>{item.mentioned?"ذُكر":"لم يُذكر"}</Badge></div>{item.competitors.length>0&&<p className="mt-2 text-xs text-text-secondary">متاجر أخرى ذُكرت: {item.competitors.slice(0,3).join("، ")}</p>}</Card>)}</div></section></>;
}
