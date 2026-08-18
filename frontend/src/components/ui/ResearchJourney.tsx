import { AgentRunSummary } from "@/lib/api";
import { BrandMark } from "./BrandMark";
import { IconCheckCircle, IconLoader } from "./icons";

type Stage={label:string;detail:string;state:"pending"|"running"|"completed"|"failed"};

export function ResearchJourney({agentRuns,waitingForWorker=false,storeUrl}:{agentRuns:AgentRunSummary[];storeId:string;waitingForWorker?:boolean;storeUrl?:string}){
 const crawl=agentRuns.find(x=>x.agent_type==="crawl_agent_run");const classification=agentRuns.find(x=>x.agent_type==="ai_classification_agent_run");
 const stages:Stage[]=[
  {label:"اكتشاف المتجر",detail:"قراءة الصفحة الرئيسية وبنية المتجر",state:stepState(crawl?.status,waitingForWorker)},
  {label:"اكتشاف التصنيفات",detail:"تحديد أقسام المنتجات والصفحات المرتبطة",state:dependentState(crawl?.status,classification?.status)},
  {label:"فهم الهوية",detail:"استخلاص النشاط والوصف والإشارات الموثقة",state:stepState(classification?.status,crawl?.status!=="completed")},
  {label:"إكمال التقرير الأساسي",detail:"تجهيز النتيجة الأولى وتوسيع القياسات لاحقًا",state:classification?.status==="completed"||classification?.status==="failed"?"completed":"pending"},
 ];
 const found=stages.findIndex(x=>x.state==="running");const activeIndex=found<0?Math.max(0,stages.filter(x=>x.state==="completed").length-1):found;
 return <div className="fixed inset-0 z-[100] overflow-y-auto bg-[#f8faff] font-sans text-[#171821]">
  <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_15%,rgba(56,189,248,.2),transparent_27%),radial-gradient(circle_at_87%_18%,rgba(99,102,241,.22),transparent_31%),linear-gradient(180deg,#eef4ff_0%,#ffffff_65%)]"/>
  <header className="relative flex items-center justify-between px-6 py-6 md:px-10"><span className="flex items-center gap-2 text-lg font-semibold"><BrandMark className="h-9 w-9"/>ظهور</span><span className="rounded-full border border-[#dfe3f4] bg-white/70 px-4 py-2 text-xs text-[#62677a]">يمكنك العودة لاحقًا — سنحفظ التقدم</span></header>
  <main className="relative mx-auto grid min-h-[calc(100vh-92px)] max-w-6xl items-center gap-10 px-6 pb-14 lg:grid-cols-[1fr_1.08fr]">
   <section className="text-right"><p className="text-sm font-semibold text-[#5b5cf0]">تحليل المتجر قيد التنفيذ</p><h1 className="mt-4 text-4xl font-semibold leading-[1.35] md:text-6xl">نحوّل موقعك إلى<br/><span className="text-transparent bg-clip-text bg-gradient-to-l from-[#4f46e5] to-[#38bdf8]">صورة واضحة للسوق</span></h1><p className="mt-5 max-w-xl text-base leading-8 text-[#62677a]">نبدأ بالصفحات الأساسية والتصنيفات لتظهر النتيجة الأولى سريعًا، ثم يستمر قياس البحث والذكاء الاصطناعي في الخلفية.</p>
    <ol className="mt-8 grid gap-2">{stages.map((stage,index)=><li key={stage.label} className={`flex items-center gap-4 rounded-2xl border px-4 py-3 transition ${stage.state==="running"?"border-[#8b8cf8] bg-white shadow-[0_12px_35px_-24px_rgba(79,70,229,.7)]":"border-[#e5e8f4] bg-white/55"}`}><span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm ${stage.state==="running"?"bg-[#5b5cf0] text-white":"bg-[#eef0ff] text-[#5b5cf0]"}`}>{index+1}</span><span className="min-w-0 flex-1"><strong className="block text-sm">{stage.label}</strong><span className="text-xs text-[#7d8295]">{stage.detail}</span></span><StageIcon state={stage.state}/></li>)}</ol>
   </section>
   <section className="relative mx-auto w-full max-w-xl animate-mersad-float"><span className="animate-mersad-ring absolute inset-8 rounded-[2.5rem] border-2 border-[#6366f1]/25"/><div className="relative overflow-hidden rounded-[2rem] border border-[#dfe3f4] bg-white p-4 shadow-[0_35px_90px_-38px_rgba(79,70,229,.55)]">
    <div className="flex items-center gap-2 border-b border-[#edf0f7] px-2 pb-3"><span className="h-2.5 w-2.5 rounded-full bg-[#fb7185]"/><span className="h-2.5 w-2.5 rounded-full bg-[#fbbf24]"/><span className="h-2.5 w-2.5 rounded-full bg-[#34d399]"/><div dir="ltr" className="ms-3 flex-1 truncate rounded-lg bg-[#f2f4fa] px-3 py-1.5 text-center text-xs text-[#777d90]">{storeUrl?.replace(/^https?:\/\//,"")??"متجرك قيد القراءة"}</div></div>
    <div className="relative mt-4 aspect-[16/10] overflow-hidden rounded-2xl bg-gradient-to-br from-[#eef2ff] via-white to-[#e5f6ff] p-5"><div className="animate-mersad-scan absolute inset-x-0 top-0 z-20 h-20 bg-gradient-to-b from-transparent via-[#5b5cf0]/20 to-[#38bdf8]/45 blur-sm"/><div className="mx-auto h-5 w-2/3 rounded-full bg-[#cdd4ff]"/><div className="mt-5 grid grid-cols-3 gap-3">{[0,1,2].map(i=><div key={i} className="rounded-xl border border-white bg-white/80 p-3 shadow-sm"><div className="aspect-square rounded-lg bg-gradient-to-br from-[#dfe3ff] to-[#dff5ff]"/><div className="mt-2 h-2 rounded bg-[#d8dcea]"/><div className="mt-1.5 h-2 w-2/3 rounded bg-[#eceef5]"/></div>)}</div><div className="mt-4 grid grid-cols-2 gap-3"><div className="h-12 rounded-xl bg-white/80"/><div className="h-12 rounded-xl bg-white/80"/></div></div>
    <div className="mt-4 flex items-center justify-between gap-4"><div><p className="text-sm font-semibold">{stages[activeIndex]?.label}</p><p className="mt-1 text-xs text-[#7d8295]">النتيجة الأولية تظهر فور جاهزيتها</p></div><span className="relative flex h-12 w-12 items-center justify-center rounded-full bg-[#eef0ff]"><IconLoader className="h-5 w-5 animate-spin text-[#5b5cf0]"/></span></div>
    <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#edf0f8]"><div className="h-full rounded-full bg-gradient-to-l from-[#4f46e5] to-[#38bdf8] transition-all duration-700" style={{width:`${Math.max(10,((activeIndex+1)/stages.length)*100)}%`}}/></div>
   </div></section>
  </main>
 </div>;
}

function stepState(status:string|undefined,waiting:boolean):Stage["state"]{if(status==="completed"||status==="failed"||status==="running")return status;return waiting?"pending":"running"}
function dependentState(first:string|undefined,second:string|undefined):Stage["state"]{if(second==="completed"||second==="failed"||second==="running")return second;return first==="completed"?"running":"pending"}
function StageIcon({state}:{state:Stage["state"]}){if(state==="completed")return <IconCheckCircle className="h-5 w-5 text-[#168b73]"/>;if(state==="failed")return <span className="text-xs text-[#b87716]">تعذر</span>;if(state==="running")return <IconLoader className="h-5 w-5 animate-spin text-[#5b5cf0]"/>;return <span className="h-2.5 w-2.5 rounded-full border border-[#c8cddd]"/>}
