"use client";
/* eslint-disable @next/next/no-img-element -- product images come from arbitrary audited store domains */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { IconArrowLeft, IconCheckCircle, IconExternal, IconStore } from "@/components/ui/icons";
import { OptimizedImageResult, ProductDetail, generateImplementation, getProductDetail, optimizeProductImage, saveImplementationDraft, waitForOnDemandJob } from "@/lib/api";

type ViewMode = "current" | "suggested" | "compare";
type FaqItem = { question:string; answer:string; confirmed:boolean; source?:string };
type DraftFields = { title:string; meta_description:string; h1:string; description:string; features:string[]; usage:string; specifications:Record<string,string>; image_alt:string; h2:string[]; faq:FaqItem[]; internal_links:string[]; instructions:string[] };
const EMPTY_DRAFT: DraftFields = {title:"",meta_description:"",h1:"",description:"",features:[],usage:"",specifications:{},image_alt:"",h2:[],faq:[],internal_links:[],instructions:[]};

export default function ProductStudioPage() {
  const { id: storeId, productId } = useParams<{ id: string; productId: string }>();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("compare");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [optimizing,setOptimizing]=useState(false);
  const [optimized,setOptimized]=useState<OptimizedImageResult|null>(null);
  const [draft, setDraft] = useState<DraftFields>(EMPTY_DRAFT);

  useEffect(() => { getProductDetail(storeId, productId).then((result) => { setProduct(result); setDraft(draftFromProduct(result)); }).catch((reason) => setError(String(reason))); }, [storeId, productId]);

  if (error) return <ErrorState message={error} />;
  if (!product) return <LoadingState label="نفتح مساحة تحسين المنتج..." />;

  const proposed = {
    title: asText(draft.title), meta_description: asText(draft.meta_description),
    h1: asText(draft.h1), description:asText(draft.description), features:draft.features,
    usage:asText(draft.usage), image_alt:asText(draft.image_alt), h2: draft.h2, faq: draft.faq,
    links: draft.internal_links, instructions: draft.instructions,
  };
  const current = {
    title: asText(product.current.title), meta_description: asText(product.current.meta_description),
    h1: asText(product.current.h1), description: asText(product.current.description),
  };
  const imageInsights = product.image_insights ?? [];
  const linkSuggestions = asLinkSuggestions(product.current.link_suggestions);
  const hasProposal = Object.values(proposed).some((value) => Array.isArray(value) ? value.length > 0 : Boolean(value));
  const prepareChange = async () => {
    const recommendation = product.recommendations[0];
    if (!recommendation) return;
    setGenerating(true);
    setError(null);
    try {
      const job = await generateImplementation(recommendation.id, "rebuild");
      await waitForOnDemandJob(storeId, job.research_run_id);
      const refreshed = await getProductDetail(storeId, productId);
      setProduct(refreshed); setDraft(draftFromProduct(refreshed));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setGenerating(false);
    }
  };
  const saveDraft = async () => {
    const recommendation = product.recommendations[0];
    if (!recommendation) return;
    setSaving(true);
    try {
      await saveImplementationDraft(recommendation.id, draft);
      const refreshed = await getProductDetail(storeId, productId);
      setProduct(refreshed); setDraft(draftFromProduct(refreshed));
    } finally { setSaving(false); }
  };
  const optimizeFirstImage=async()=>{const image=imageInsights[0];if(!image)return;setOptimizing(true);setError(null);try{setOptimized(await optimizeProductImage(storeId,productId,image.url))}catch(reason){setError(String(reason))}finally{setOptimizing(false)}};

  return <div className="flex flex-col gap-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><Link href={`/stores/${storeId}/products`} className="mb-3 inline-flex items-center gap-1 text-sm text-text-secondary"><IconArrowLeft className="h-4 w-4 rotate-180" />كل المنتجات</Link><p className="text-xs font-semibold text-primary">استوديو تحسين المنتج</p><h1 className="mt-1 text-2xl font-bold text-text">{product.name}</h1><a href={product.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-text-tertiary hover:text-primary"><IconExternal className="h-4 w-4" />فتح الصفحة الأصلية</a></div>
      <div className="flex items-center gap-3"><div className="text-left"><p className="text-2xl font-bold text-primary">{product.completion_score}%</p><p className="text-xs text-text-tertiary">اكتمال الصفحة</p></div><div className="h-12 w-12 overflow-hidden rounded-xl bg-neutral-tint">{product.image_url ? <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" /> : <IconStore className="m-3 h-6 w-6" />}</div></div>
    </header>

    <section className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,.8fr)]">
      <div className="space-y-4">
        <GooglePreview url={product.url} title={proposed.title || current.title || product.name} description={proposed.meta_description || current.meta_description} />
        <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex rounded-xl border border-border bg-white p-1 text-sm">{(["current", "suggested", "compare"] as ViewMode[]).map((item) => <button key={item} onClick={() => setMode(item)} className={`rounded-lg px-4 py-2 ${mode === item ? "bg-primary text-white" : "text-text-secondary"}`}>{item === "current" ? "الحالية" : item === "suggested" ? "المقترحة" : "قبل وبعد"}</button>)}</div><div className="flex gap-2 text-xs"><button onClick={() => setDevice("desktop")} className={`rounded-lg border px-3 py-2 ${device === "desktop" ? "border-primary text-primary" : "border-border"}`}>سطح المكتب</button><button onClick={() => setDevice("mobile")} className={`rounded-lg border px-3 py-2 ${device === "mobile" ? "border-primary text-primary" : "border-border"}`}>الجوال</button></div></div>
        <div className={`grid gap-4 ${mode === "compare" ? "lg:grid-cols-2" : "grid-cols-1"}`}>
          {(mode === "current" || mode === "compare") && <LivePagePreview product={product} device={device} />}
          {(mode === "suggested" || mode === "compare") && <ProductPreview label="النسخة المقترحة" product={product} title={proposed.h1 || current.h1 || product.name} description={proposed.description || proposed.meta_description || current.description} sections={proposed.h2} faq={proposed.faq} device={device} empty={!hasProposal} />}
        </div>
      </div>

      <aside className="space-y-4">
        <Card padding="lg"><div className="flex items-center justify-between"><h2 className="font-bold text-text">تشخيص الصفحة</h2><Badge variant={product.checks.some((check) => check.status === "missing") ? "warning" : "success"}>{product.checks.filter((check) => check.status === "missing").length} تحتاج مراجعة</Badge></div><div className="mt-4 space-y-3">{product.checks.map((check) => <div key={check.key} className="rounded-xl border border-border p-3"><div className="flex items-start gap-3"><span className={`mt-0.5 rounded-full p-1 ${check.status === "present" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}><IconCheckCircle className="h-4 w-4" /></span><div><p className="text-sm font-semibold text-text">{check.label}</p><p className="mt-1 text-xs leading-5 text-text-secondary">{check.message}</p>{check.current_value && <p className="mt-2 line-clamp-2 rounded-lg bg-neutral-tint p-2 text-xs text-text-tertiary">{check.current_value}</p>}</div></div></div>)}</div></Card>
        <Card padding="lg"><div className="flex items-center justify-between gap-3"><h2 className="font-bold text-text">التعديلات الجاهزة</h2>{product.recommendations[0] && <button onClick={prepareChange} disabled={generating} className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{generating ? "نجهّز التعديل..." : hasProposal ? "إعادة تجهيز" : "جهّز التعديل"}</button>}</div>{hasProposal ? <div className="mt-4 space-y-4"><EditorField label="العنوان" current={current.title} value={draft.title} onChange={(value) => setDraft({...draft,title:value})} /><EditorField label="Meta description" current={current.meta_description} value={draft.meta_description} multiline onChange={(value) => setDraft({...draft,meta_description:value})} /><EditorField label="H1" current={current.h1} value={draft.h1} onChange={(value) => setDraft({...draft,h1:value})} /><EditorField label="وصف المنتج" current={current.description} value={draft.description} multiline onChange={(value) => setDraft({...draft,description:value})} /><ListEditor label="المزايا والفوائد" value={draft.features} onChange={(value) => setDraft({...draft,features:value})} /><EditorField label="طريقة الاستخدام" current={null} value={draft.usage} multiline onChange={(value) => setDraft({...draft,usage:value})} /><EditorField label="النص البديل للصورة الرئيسية" current={null} value={draft.image_alt} onChange={(value) => setDraft({...draft,image_alt:value})} /><ListEditor label="H2 المقترحة" value={draft.h2} onChange={(value) => setDraft({...draft,h2:value})} /><FaqEditor value={draft.faq} onChange={(value) => setDraft({...draft,faq:value})} /><ListEditor label="الروابط الداخلية" value={draft.internal_links} onChange={(value) => setDraft({...draft,internal_links:value})} />{proposed.instructions.length > 0 && <ListBlock title="خطوات التنفيذ" items={proposed.instructions} />}<div className="flex flex-wrap gap-2"><button onClick={saveDraft} disabled={saving} className="rounded-lg border border-primary px-3 py-2 text-xs font-semibold text-primary disabled:opacity-50">{saving ? "نحفظ..." : "حفظ كمسودة"}</button>{product.recommendations[0] && <Link href={`/stores/${storeId}/recommendations/${product.recommendations[0].id}`} className="inline-flex items-center gap-1 px-2 text-sm font-semibold text-primary">فتح التوصية ودليلها <IconArrowLeft className="h-4 w-4" /></Link>}</div></div> : <div className="mt-4 rounded-xl border border-dashed border-border p-4 text-sm leading-6 text-text-secondary">لا توجد حزمة تنفيذ مرتبطة بهذه الصفحة بعد. لن ينشئ ظهور نصًا أو FAQ من دون توصية مدعومة بالأدلة.</div>}</Card>
        {imageInsights.length > 0 && <Card padding="lg"><div className="flex items-center justify-between"><h2 className="font-bold text-text">تحليل صور الصفحة</h2><Badge variant={imageInsights.some((image)=>image.status==="review")?"warning":"success"}>{imageInsights.filter((image)=>image.status==="review").length} تحتاج مراجعة</Badge></div><p className="mt-2 text-xs leading-5 text-text-tertiary">نعرض ما قسناه من الصفحة فقط. حجم الملف وصيغة الضغط لا يُحكمان قبل قياسهما.</p><div className="mt-4 grid grid-cols-2 gap-3">{imageInsights.slice(0, 8).map((image,index) => <div key={`${image.url}-${index}`} className="overflow-hidden rounded-xl border border-border"><div className="aspect-square bg-neutral-tint"><img src={image.url} alt={image.alt || ""} className="h-full w-full object-cover" /></div><div className="space-y-2 p-2"><p className="truncate text-[11px] text-text-secondary">{image.alt || "لا يوجد alt مؤكد"}</p><p className="text-[10px] text-text-tertiary">{image.width && image.height ? `${image.width} × ${image.height}` : "الأبعاد غير متاحة"}</p><div className="flex flex-wrap gap-1">{image.issues.map((issue)=><span key={issue} className="rounded bg-warning/10 px-1.5 py-1 text-[9px] text-warning">{imageIssueLabel(issue)}</span>)}{image.issues.length===0&&<span className="rounded bg-success/10 px-1.5 py-1 text-[9px] text-success">لا توجد مشكلة مرصودة</span>}</div></div></div>)}</div></Card>}
        {imageInsights.length>0&&<Card padding="lg"><h2 className="font-bold text-text">نسخة صورة محسّنة</h2><p className="mt-2 text-xs leading-5 text-text-secondary">تُنشأ عند الطلب بصيغة WebP ولا تُنشر في المتجر.</p><button onClick={optimizeFirstImage} disabled={optimizing} className="mt-3 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{optimizing?"نعالج الصورة...":"إنشاء نسخة محسّنة"}</button>{optimized&&<div className="mt-4 rounded-xl bg-success/5 p-3 text-xs text-text-secondary"><p>قبل: {formatBytes(optimized.original_bytes)} — بعد: {formatBytes(optimized.optimized_bytes)}</p><p className="mt-1 font-semibold text-success">توفير {optimized.saved_percent}%</p><a href={optimized.download_url} className="mt-3 inline-block font-semibold text-primary">تنزيل WebP</a></div>}</Card>}
        {linkSuggestions.length>0&&<Card padding="lg"><h2 className="font-bold text-text">روابط داخلية مقترحة من المتجر</h2><p className="mt-2 text-xs text-text-tertiary">منتجات وتصنيفات مرصودة فعلًا، وليست روابط مولدة.</p><div className="mt-3 space-y-2">{linkSuggestions.map((link)=><div key={link.url} className="flex items-center justify-between gap-3 rounded-lg border border-border p-2"><span className="truncate text-xs text-text-secondary">{link.label}</span><button onClick={()=>setDraft({...draft,internal_links:Array.from(new Set([...draft.internal_links,link.url]))})} className="shrink-0 text-xs font-semibold text-primary">إضافة</button></div>)}</div></Card>}
        <SchemaPreview product={product} />
      </aside>
    </section>
  </div>;
}

function ProductPreview({label, product, title, description, sections=[], faq=[], device, empty=false}:{label:string;product:ProductDetail;title:string|null;description:string|null;sections?:string[];faq?:FaqItem[];device:"desktop"|"mobile";empty?:boolean}) {
  return <div className={`mx-auto w-full overflow-hidden rounded-[1.75rem] border border-border bg-white shadow-sm ${device === "mobile" ? "max-w-sm" : "max-w-none"}`}><div className="flex items-center justify-between border-b border-border px-5 py-3"><span className="text-xs font-semibold text-text-secondary">{label}</span><span className="h-2 w-2 rounded-full bg-success" /></div><div className={`grid gap-6 p-5 ${device === "desktop" ? "md:grid-cols-2" : "grid-cols-1"}`}><div className="aspect-square overflow-hidden rounded-2xl bg-neutral-tint">{product.image_url ? <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center"><IconStore className="h-8 w-8 text-text-tertiary" /></div>}</div><div className="flex flex-col justify-center"><h2 className="text-xl font-bold text-text">{title || product.name}</h2>{product.price !== null && <p className="mt-2 font-semibold text-primary">{product.price} {product.currency ?? ""}</p>}<p className="mt-4 text-sm leading-7 text-text-secondary">{description || "لم نرصد وصفًا مؤكدًا لهذه الصفحة."}</p><button className="mt-5 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white">إضافة إلى السلة — معاينة</button></div></div>{sections.length > 0 && <div className="border-t border-border px-5 py-5"><ListBlock title="أقسام الصفحة المقترحة" items={sections} /></div>}{faq.length > 0 && <div className="border-t border-border px-5 py-5"><ListBlock title="الأسئلة الشائعة" items={faq.map((item)=>item.answer ? `${item.question} — ${item.answer}` : item.question)} /></div>}{empty && <div className="border-t border-warning/20 bg-warning/5 p-4 text-center text-xs text-text-secondary">هذه المعاينة تستخدم البيانات الحالية حتى تتوفر حزمة تنفيذ مدعومة بالأدلة.</div>}</div>;
}

function LivePagePreview({product, device}:{product:ProductDetail;device:"desktop"|"mobile"}) {
  return <div className={`mx-auto w-full overflow-hidden rounded-[1.75rem] border border-border bg-white shadow-sm ${device === "mobile" ? "max-w-sm" : "max-w-none"}`}><div className="flex items-center justify-between border-b border-border px-5 py-3"><span className="text-xs font-semibold text-text-secondary">الصفحة الأصلية</span><a href={product.url} target="_blank" rel="noreferrer" className="text-xs text-primary">فتح خارجيًا</a></div><iframe src={product.url} title={`صفحة ${product.name}`} className="h-[42rem] w-full bg-white" sandbox="allow-same-origin allow-scripts" /><div className="border-t border-border bg-neutral-tint p-3 text-center text-[11px] text-text-tertiary">إذا منع المتجر العرض داخل ظهور، استخدم «فتح خارجيًا». تبقى بيانات التحليل مأخوذة من آخر قراءة موثقة.</div></div>;
}

function GooglePreview({url,title,description}:{url:string;title:string;description:string|null}) { let host=url;try{host=new URL(url).hostname}catch{}return <Card padding="lg"><p className="text-xs font-semibold text-text-tertiary">معاينة Google</p><p dir="ltr" className="mt-3 text-left text-xs text-success">{host}</p><h2 className="mt-1 text-lg font-medium text-[#1a0dab]">{title}</h2><p className="mt-1 line-clamp-2 text-sm leading-6 text-text-secondary">{description || "لا يوجد وصف مقترح أو مرصود لعرضه."}</p></Card>; }
function SchemaPreview({product}:{product:ProductDetail}) { const schema:Record<string,unknown>={"@context":"https://schema.org","@type":"Product",name:product.name,url:product.url};if(product.image_url)schema.image=product.image_url;if(product.price!==null)schema.offers={"@type":"Offer",price:product.price,...(product.currency?{priceCurrency:product.currency}:{}),...(product.availability?{availability:product.availability}:{})};const code=JSON.stringify(schema,null,2);return <Card padding="lg"><div className="flex items-center justify-between gap-3"><div><h2 className="font-bold text-text">Product Schema</h2><p className="mt-1 text-xs text-text-tertiary">مولدة من حقول المنتج المؤكدة فقط.</p></div><button onClick={()=>navigator.clipboard.writeText(code)} className="rounded-lg border border-border px-3 py-2 text-xs font-semibold text-primary">نسخ JSON-LD</button></div><pre dir="ltr" className="mt-4 max-h-64 overflow-auto rounded-xl bg-[#111827] p-4 text-left text-[11px] leading-5 text-[#d1fae5]">{code}</pre></Card>; }
function EditorField({label,current,value,onChange,multiline=false}:{label:string;current:string|null;value:string;onChange:(value:string)=>void;multiline?:boolean}) { const cls="mt-2 w-full rounded-lg border border-primary/20 bg-primary-tint p-3 text-xs text-text outline-none focus:border-primary";return <div><p className="text-xs font-semibold text-text-tertiary">{label}</p><div className="mt-2 rounded-lg bg-neutral-tint p-3 text-xs text-text-secondary"><span className="mb-1 block text-[10px] text-text-tertiary">الحالي</span>{current || "غير متوفر"}</div>{multiline?<textarea rows={4} value={value} onChange={(event)=>onChange(event.target.value)} className={cls} placeholder="لا يوجد مقترح مدعوم بعد"/>:<input value={value} onChange={(event)=>onChange(event.target.value)} className={cls} placeholder="لا يوجد مقترح مدعوم بعد"/>}</div>; }
function ListEditor({label,value,onChange}:{label:string;value:string[];onChange:(value:string[])=>void}) { return <div><p className="mb-2 text-xs font-semibold text-text-tertiary">{label}</p><textarea rows={5} value={value.join("\n")} onChange={(event)=>onChange(event.target.value.split("\n").map((item)=>item.trim()).filter(Boolean))} className="w-full rounded-lg border border-primary/20 bg-primary-tint p-3 text-xs leading-6 text-text outline-none focus:border-primary" placeholder="عنصر واحد في كل سطر"/></div>; }
function FaqEditor({value,onChange}:{value:FaqItem[];onChange:(value:FaqItem[])=>void}) { const update=(index:number,key:"question"|"answer",text:string)=>onChange(value.map((item,itemIndex)=>itemIndex===index?{...item,[key]:text}:item));return <div><div className="mb-2 flex items-center justify-between"><p className="text-xs font-semibold text-text-tertiary">الأسئلة الشائعة</p><button type="button" onClick={()=>onChange([...value,{question:"",answer:"",confirmed:false}])} className="text-xs font-semibold text-primary">+ إضافة سؤال</button></div><div className="space-y-3">{value.map((item,index)=><div key={index} className="rounded-xl border border-border p-3"><input value={item.question} onChange={(event)=>update(index,"question",event.target.value)} className="w-full rounded-lg border border-primary/20 bg-primary-tint p-2 text-xs" placeholder="السؤال"/><textarea rows={3} value={item.answer} onChange={(event)=>update(index,"answer",event.target.value)} className="mt-2 w-full rounded-lg border border-primary/20 bg-primary-tint p-2 text-xs" placeholder="الإجابة المدعومة بالمعلومات المتوفرة"/><label className="mt-2 flex items-center gap-2 text-[11px] text-text-secondary"><input type="checkbox" checked={item.confirmed||Boolean(item.source)} disabled={Boolean(item.source)} onChange={(event)=>onChange(value.map((row,itemIndex)=>itemIndex===index?{...row,confirmed:event.target.checked}:row))}/>{item.source?"مرتبطة بمصدر محفوظ":"أؤكد صحة هذه الإجابة"}</label><button type="button" onClick={()=>onChange(value.filter((_,itemIndex)=>itemIndex!==index))} className="mt-2 text-[11px] text-danger">حذف</button></div>)}</div></div>; }
function ListBlock({title,items}:{title:string;items:string[]}) { return <div><h3 className="text-sm font-semibold text-text">{title}</h3><ul className="mt-2 space-y-2">{items.map((item,index) => <li key={`${item}-${index}`} className="flex gap-2 text-xs leading-5 text-text-secondary"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{item}</li>)}</ul></div>; }
function asText(value:unknown):string|null { return typeof value === "string" && value.trim() ? value.trim() : null; }
function asList(value:unknown):string[] { if (Array.isArray(value)) return value.map((item) => typeof item === "string" ? item : JSON.stringify(item)).filter(Boolean); return value ? [String(value)] : []; }
function asFaq(value:unknown):FaqItem[] { if (!Array.isArray(value)) return []; return value.map((item)=>{if(typeof item==="string")return {question:item,answer:"",confirmed:false};if(item&&typeof item==="object"){const row=item as Record<string,unknown>;return {question:asText(row.question)??"",answer:asText(row.answer)??"",confirmed:row.confirmed===true,source:asText(row.source)??undefined};}return {question:"",answer:"",confirmed:false};}).filter((item)=>item.question||item.answer); }
function imageIssueLabel(issue:string):string { return ({missing_alt:"alt مفقود",dimensions_unknown:"الأبعاد غير متاحة",small_dimensions:"أبعاد صغيرة",large_dimensions_review:"أبعاد كبيرة تحتاج مراجعة",duplicate_source:"مصدر صورة مكرر"} as Record<string,string>)[issue]??issue; }
function asLinkSuggestions(value:unknown):Array<{label:string;url:string;kind:string}>{if(!Array.isArray(value))return[];return value.filter((item):item is Record<string,unknown>=>!!item&&typeof item==="object"&&typeof item.url==="string").map((item)=>({label:typeof item.label==="string"?item.label:String(item.url),url:String(item.url),kind:typeof item.kind==="string"?item.kind:"page"}))}
function formatBytes(value:number):string{return value>=1024*1024?`${(value/1024/1024).toFixed(1)} MB`:`${Math.round(value/1024)} KB`}
function draftFromProduct(product:ProductDetail):DraftFields { const implementation=product.recommendations.find((item)=>Object.keys(item.implementation).length)?.implementation??{};return {title:asText(implementation.title)??"",meta_description:asText(implementation.meta_description)??"",h1:asText(implementation.h1)??"",description:asText(implementation.description)??"",features:asList(implementation.features),usage:asText(implementation.usage)??"",specifications:asRecord(implementation.specifications),image_alt:asText(implementation.image_alt)??"",h2:asList(implementation.h2),faq:asFaq(implementation.faq),internal_links:asList(implementation.internal_links),instructions:asList(implementation.instructions)}; }
function asRecord(value:unknown):Record<string,string>{if(!value||typeof value!=="object"||Array.isArray(value))return{};return Object.fromEntries(Object.entries(value).filter((entry):entry is [string,string]=>typeof entry[1]==="string"&&Boolean(entry[1].trim())))}
