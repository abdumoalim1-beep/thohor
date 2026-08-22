"use client";

import Link from "next/link";
import { type CSSProperties, useEffect, useState } from "react";

import { BrandMark } from "@/components/ui/BrandMark";
import { joinBetaDirectly } from "@/lib/api";

import "./landing.css";

// ---------------------------------------------------------------------------
// "Zuhoor Landing" design handoff (2026-08-22) — colors, spacing and copy
// below are ported 1:1 from the approved mockup, not the site's older
// var(--acc)/var(--tx) token system. Only the hero's link input + "ابدأ
// الآن" button is intentionally NOT from the mockup (which had two plain
// buttons there) — that's the live domain -> /preview analysis flow and is
// carried over unchanged from the previous homepage per explicit instruction.
// ---------------------------------------------------------------------------

const TEAL = "#0b9e94";
const TEAL_BRIGHT = "#0fd6c2";
const TEAL_DEEP = "#066a63";
const DARK = "#042b29";
const MUTED = "#5c6a69";
const MUTED2 = "#3c4b4a";
const BORDER = "#eff4f3";
const CARD_BG = "#f6faf9";
const GOOD_BG = "#eefaf5";
const GOOD_FG = "#19a06a";

const WORDS = ["إيرادات", "أرباح", "عملاء"];

const NAV_LINKS: { label: string; href: string }[] = [
  { label: "الرئيسية", href: "#top" },
  { label: "المنصة", href: "#how" },
  { label: "الحلول", href: "#features" },
  { label: "الأسعار", href: "#pricing" },
  { label: "من نحن", href: "#testimonials" },
  { label: "تواصل", href: "#footer" },
];

const DASHBOARD_NAV_ITEMS: { icon: DashIconName; label: string; active?: boolean }[] = [
  { icon: "grid", label: "نظرة عامة", active: true },
  { icon: "eye", label: "الظهور" },
  { icon: "bolt", label: "فرص التحسين" },
  { icon: "pen", label: "المحتوى" },
  { icon: "users", label: "المنافسون" },
  { icon: "doc", label: "التقارير" },
  { icon: "gear", label: "الإعدادات" },
];

// The 5 quick stats deliberately roll every AI engine up into one "AI"
// number — the per-engine split lives in its own card below, so this row
// stays a summary instead of turning into a wall of numbers.
const QUICK_STATS: { icon: DashIconName; value: string; label: string; delta?: string; highlight?: boolean }[] = [
  { icon: "gauge", value: "64%", label: "مؤشر الظهور", delta: "↑12%" },
  { icon: "search", value: "72%", label: "Google" },
  { icon: "spark", value: "53%", label: "AI" },
  { icon: "users", value: "5", label: "المنافسون" },
  { icon: "bolt", value: "12", label: "فرص التحسين", highlight: true },
];

const BAR_A = [38, 54, 42, 66, 58, 80, 62, 88, 70, 96, 76, 92];
const BAR_B = [22, 40, 30, 48, 36, 58, 44, 66, 50, 72, 54, 68];
const BARS = BAR_A.map((a, i) => ({ a, b: BAR_B[i] }));
const MONTHS = ["ينا", "فبر", "مار", "أبر", "ماي", "يون", "يول", "أغس", "سبت", "أكت", "نوف", "ديس"];

// Visibility trend: your own line climbs toward the 64% headline number
// while the competitor bars stay flat — the whole point of the chart is
// "you're closing the gap", so the series are shaped to show exactly that.
const TREND_MAX = 80;
const TREND_SERIES: { label: string; swatch: string; bar: string; values: number[] }[] = [
  {
    label: "موقعك",
    swatch: TEAL,
    bar: "linear-gradient(180deg,#0bbfb1,#7fdcd4)",
    values: [28, 32, 30, 38, 42, 40, 48, 52, 50, 58, 62, 64],
  },
  { label: "المتوسط", swatch: "#dbe6e5", bar: "#dbe6e5", values: [42, 44, 41, 45, 43, 46, 44, 47, 45, 46, 44, 45] },
  { label: "الأفضل", swatch: "#9db5b3", bar: "#9db5b3", values: [62, 64, 63, 66, 65, 68, 66, 69, 67, 70, 68, 71] },
];

const AI_ENGINES: { name: string; pct: number; up: boolean; icon: DashIconName; color: string }[] = [
  { name: "ChatGPT", pct: 61, up: true, icon: "chat", color: "#0b9e94" },
  { name: "Gemini", pct: 54, up: true, icon: "spark", color: "#8B5CF6" },
  { name: "Perplexity", pct: 46, up: false, icon: "orbit", color: "#F0A34D" },
];

const OPPORTUNITIES: { title: string; reason: string; impact: string; engine: string; action: string }[] = [
  { title: "تحسين صفحة الخدمات", reason: "غائب عن 12 سؤالًا", impact: "مرتفع", engine: "ChatGPT + Google", action: "تحسين" },
  { title: "إنشاء مقال", reason: "منافسوك يظهرون وأنت لا", impact: "مرتفع", engine: "AI", action: "إنشاء" },
];

const MARQUEE_BASE = ["شعار", "منصة", "مجموعة", "شركة", "مؤسسة", "استوديو", "مختبر", "وكالة"];
const MARQUEE_LOGOS = [...MARQUEE_BASE, ...MARQUEE_BASE];

const SCORE_ROWS: { label: string; value: string; width: string }[] = [
  { label: "الوصول", value: "٨٢٪", width: "82%" },
  { label: "الانطباع الإيجابي", value: "٧٤٪", width: "74%" },
  { label: "حصة الصوت", value: "٦١٪", width: "61%" },
];

const SPARKLINE = [42, 66, 54, 78, 60, 88, 70, 96, 74, 90];

const REPORT_ROWS: { icon: string; title: string; value: string; delta: string }[] = [
  { icon: "📰", title: "الأخبار والصحافة", value: "٤٨٢٦ إشارة", delta: "+١٢٪" },
  { icon: "📱", title: "التواصل الاجتماعي", value: "١٢٩٠٤ إشارة", delta: "+٨٪" },
  { icon: "🎙", title: "البودكاست", value: "٣١٨ إشارة", delta: "+٥٪" },
  { icon: "📺", title: "الفيديو", value: "١٢٤٠ إشارة", delta: "+٩٪" },
];

const FEATURES: { icon: string; title: string; text: string }[] = [
  { icon: "📡", title: "متابعة التغطية الإعلامية", text: "تابع علامتك في الأخبار والتواصل الاجتماعي والفيديو والبودكاست في مكان واحد." },
  { icon: "📈", title: "ظهور لحظي", text: "راقب الإشارات والوصول وحصة الصوت لحظة بلحظة." },
  { icon: "🛡", title: "تنبيهات ذكية", text: "إشعار فوري عند تغيّر الانطباع أو ظهور ارتفاع مفاجئ." },
  { icon: "📋", title: "تقارير تلقائية", text: "أنشئ تقارير علامة جاهزة للعرض وفق جدول زمني." },
  { icon: "👁", title: "رؤى الظهور", text: "اعرف القنوات التي تجلب أكبر قدر من الانتباه لعلامتك." },
  { icon: "👥", title: "عمل جماعي", text: "أضف فريقك، ووزّع الإشارات، وحافظ على تنسيق التقارير." },
];

const TESTIMONIALS: { quote: string; name: string; company: string }[] = [
  { quote: "وفّرنا أسابيع من المتابعة اليدوية، ولوحة التحكم تجعل الأمر بسيطاً.", name: "سارة النديّة", company: "إيرث أوبس" },
  { quote: "سريعة وموثوقة وممتعة في الاستخدام فعلاً، وفريق التسويق أحبّها.", name: "ليو تاناكا", company: "فيوتشر ون" },
];

type PricingPlan = {
  name: string;
  price: string;
  desc: string;
  cta: string;
  features: string[];
  bg: string;
  border: string;
  boxShadow: string;
  nameColor: string;
  priceColor: string;
  mutedColor: string;
  featColor: string;
  checkColor: string;
  btnBg: string;
  btnColor: string;
  btnBorder: string;
};

const PLAN_LIGHT = {
  bg: "#fff",
  border: `1px solid ${BORDER}`,
  boxShadow: "0 2px 4px rgba(4,43,41,0.02),0 16px 40px rgba(4,43,41,0.04)",
  nameColor: TEAL,
  priceColor: DARK,
  mutedColor: MUTED,
  featColor: "#33433f",
  checkColor: TEAL,
  btnBg: "#fff",
  btnColor: "#0b8f86",
  btnBorder: "1px solid #cdeeea",
};

const PLANS: PricingPlan[] = [
  {
    ...PLAN_LIGHT,
    name: "البداية",
    price: "١٨٩",
    desc: "للفرق الصغيرة التي تبدأ بمتابعة ظهور علامتها.",
    cta: "ابدأ المتابعة",
    features: ["متابعة حجم الإشارات", "تقرير واحد شهرياً", "لوحة تحكم أساسية", "دعم بالبريد"],
  },
  {
    name: "النمو",
    price: "٣٤٩",
    desc: "للفرق التي توسّع متابعة علامتها عبر القنوات.",
    cta: "ترقية الخطة",
    bg: `linear-gradient(160deg,${TEAL_BRIGHT},${TEAL_DEEP})`,
    border: "none",
    boxShadow: "0 26px 60px rgba(6,106,99,0.3)",
    nameColor: "#bff2ec",
    priceColor: "#fff",
    mutedColor: "#d6f4f1",
    featColor: "#eafaf8",
    checkColor: "#bff2ec",
    btnBg: "#fff",
    btnColor: TEAL_DEEP,
    btnBorder: "none",
    features: ["كل ما في البداية", "تقارير غير محدودة", "متابعة ظهور لحظية", "هوية مخصصة للتقارير", "دعم فوري بالأولوية"],
  },
  {
    ...PLAN_LIGHT,
    name: "المؤسسات",
    price: "٦٩٩",
    desc: "للشركات ذات احتياجات المتابعة المتقدمة.",
    cta: "اطلب وصولاً كاملاً",
    features: ["كل ما في النمو", "صلاحيات وأدوار للفريق", "حزمة تقارير للإدارة", "واجهات برمجية وتكاملات", "مدير نجاح مخصص"],
  },
];

const FAQS: string[] = [
  "كيف تحسب منصة ظهور مستوى الظهور؟",
  "هل يمكنني إنشاء تقارير جاهزة للإدارة؟",
  "هل المنصة مناسبة للعلامات الناشئة؟",
  "هل يمكن لفريقي كامل الوصول للمنصة؟",
  "هل أحتاج خبرة تقنية لاستخدام ظهور؟",
];

const JOIN_INTEREST_OPTIONS: { value: string; label: string }[] = [
  { value: "search_visibility", label: "تتبع ظهوري في نتائج البحث" },
  { value: "ai_visibility", label: "تتبع ظهوري في إجابات الذكاء الاصطناعي" },
  { value: "competitors", label: "مراقبة المنافسين" },
  { value: "content_recs", label: "التوصيات والتحسينات" },
  { value: "exploring", label: "أستكشف بس" },
];

const JOIN_USAGE_OPTIONS: { value: string; label: string }[] = [
  { value: "very_interested", label: "مهتم جدًا" },
  { value: "interested", label: "مهتم" },
  { value: "might_try", label: "ممكن أجربه" },
  { value: "not_sure", label: "مو متأكد" },
  { value: "not_interested", label: "غير مهتم حاليًا" },
];

export default function Home() {
  const [domain, setDomain] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [rotIndex, setRotIndex] = useState(0);
  const [rotOn, setRotOn] = useState(true);

  useEffect(() => {
    const timer = setInterval(() => {
      setRotOn(false);
      const swap = setTimeout(() => {
        setRotIndex((i) => (i + 1) % WORDS.length);
        setRotOn(true);
      }, 350);
      return () => clearTimeout(swap);
    }, 2600);
    return () => clearInterval(timer);
  }, []);

  return (
    <div dir="rtl" className="rasid-landing" style={{ position: "relative", minHeight: "100vh", background: "#fff", overflowX: "clip" }}>
      <HeroBlock
        domain={domain}
        onDomainChange={setDomain}
        onOpenModal={() => setModalOpen(true)}
        rotWord={WORDS[rotIndex]}
        rotOn={rotOn}
      />
      <HowItWorks />
      <FeaturesSection />
      <TestimonialsSection />
      <PricingSection />
      <FaqSection />
      <CtaBanner onOpenModal={() => setModalOpen(true)} />
      <SiteFooter />
      <JoinModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}

function SectionBadge({ label }: { label: string }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        background: "#f2faf9",
        border: "1px solid #dff2f0",
        borderRadius: 24,
        padding: "7px 18px",
        fontSize: 13,
        fontWeight: 600,
        color: "#0b8f86",
        marginBottom: 22,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: TEAL_BRIGHT }} />
      {label}
    </div>
  );
}

type DashIconName =
  | "grid"
  | "eye"
  | "bolt"
  | "pen"
  | "users"
  | "doc"
  | "gear"
  | "gauge"
  | "search"
  | "spark"
  | "chat"
  | "orbit"
  | "bell";

// Line icons for the hero's product mock. The AI-engine ones (chat /
// spark / orbit) are deliberately generic marks in our own style, not
// reproductions of the ChatGPT / Gemini / Perplexity logos — same
// trademark reasoning as the platform icons the old homepage used.
function DashIcon({ name, color = "currentColor" }: { name: DashIconName; color?: string }) {
  const c = { width: "100%", height: "100%", viewBox: "0 0 24 24", fill: "none" as const };
  const s = { stroke: color, strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "grid":
      return (
        <svg {...c}>
          <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="2.2" {...s} />
          <rect x="13" y="3.5" width="7.5" height="7.5" rx="2.2" {...s} />
          <rect x="3.5" y="13" width="7.5" height="7.5" rx="2.2" {...s} />
          <rect x="13" y="13" width="7.5" height="7.5" rx="2.2" {...s} />
        </svg>
      );
    case "eye":
      return (
        <svg {...c}>
          <path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z" {...s} />
          <circle cx="12" cy="12" r="2.9" {...s} />
        </svg>
      );
    case "bolt":
      return (
        <svg {...c}>
          <path d="M13.2 2.5L4.5 13.4h6.1l-.8 8.1 8.7-10.9h-6.1l.8-8.1z" {...s} />
        </svg>
      );
    case "pen":
      return (
        <svg {...c}>
          <path d="M4.5 19.5l1-4.6L14.7 5.7l3.6 3.6-9.2 9.2-4.6 1z" {...s} />
          <path d="M13.2 7.2l3.6 3.6" {...s} />
        </svg>
      );
    case "users":
      return (
        <svg {...c}>
          <circle cx="9.2" cy="8.4" r="3.2" {...s} />
          <path d="M3.2 19.3c0-3.2 2.7-5.3 6-5.3s6 2.1 6 5.3" {...s} />
          <path d="M16.4 6.2a3 3 0 010 5.8M18.6 19.3c0-2.5-.9-4-2.5-4.9" {...s} />
        </svg>
      );
    case "doc":
      return (
        <svg {...c}>
          <path d="M6 3.5h7.4L19 9.1V20.5H6z" {...s} />
          <path d="M13.2 3.7V9.2h5.5" {...s} />
          <path d="M9.2 13.2h6M9.2 16.6h4" {...s} />
        </svg>
      );
    case "gear":
      return (
        <svg {...c}>
          <circle cx="12" cy="12" r="3" {...s} />
          <path d="M12 2.9v2.4M12 18.7v2.4M21.1 12h-2.4M5.3 12H2.9M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7M18.4 18.4l-1.7-1.7M7.3 7.3L5.6 5.6" {...s} />
        </svg>
      );
    case "gauge":
      return (
        <svg {...c}>
          <path d="M3.8 17.6a9 9 0 1116.4 0" {...s} />
          <path d="M12 13.4l4.1-3.5" {...s} />
          <circle cx="12" cy="14.2" r="1.4" fill={color} stroke="none" />
        </svg>
      );
    case "search":
      return (
        <svg {...c}>
          <circle cx="10.6" cy="10.6" r="6.4" {...s} />
          <path d="M19.4 19.4l-4.2-4.2" {...s} />
        </svg>
      );
    case "spark":
      return (
        <svg {...c}>
          <path d="M11 2.8l1.7 5 5 1.7-5 1.7-1.7 5-1.7-5-5-1.7 5-1.7 1.7-5z" {...s} />
          <path d="M18.2 15.4l.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7.7-2.1z" {...s} />
        </svg>
      );
    case "chat":
      return (
        <svg {...c}>
          <path d="M4 5.6h16v10.2h-9.8L6 19.5v-3.7H4z" {...s} />
          <path d="M8.6 10.7h6.8" {...s} />
        </svg>
      );
    case "orbit":
      return (
        <svg {...c}>
          <circle cx="12" cy="12" r="3.4" {...s} />
          <ellipse cx="12" cy="12" rx="9" ry="4.4" {...s} />
        </svg>
      );
    case "bell":
      return (
        <svg {...c}>
          <path d="M6.3 10.1a5.7 5.7 0 1111.4 0c0 3.9 1.6 5.5 1.6 5.5H4.7s1.6-1.6 1.6-5.5z" {...s} />
          <path d="M10.2 18.6a2 2 0 003.6 0" {...s} />
        </svg>
      );
  }
}

function HeroBlock({
  domain,
  onDomainChange,
  onOpenModal,
  rotWord,
  rotOn,
}: {
  domain: string;
  onDomainChange: (v: string) => void;
  onOpenModal: () => void;
  rotWord: string;
  rotOn: boolean;
}) {
  return (
    <div
      id="top"
      style={{
        width: "100%",
        backgroundColor: "#ecf8f7",
        backgroundImage:
          "linear-gradient(to right, rgba(4,43,41,0.06) 1px, transparent 1px),linear-gradient(to bottom, rgba(4,43,41,0.06) 1px, transparent 1px),radial-gradient(120% 90% at 50% -10%, #0fd6c2 0%, #29c9bd 30%, #a9e8e2 58%, rgba(236,248,247,0.85) 78%, rgba(255,255,255,0.95) 100%)",
        backgroundSize: "64px 64px, 64px 64px, 100% 100%",
        padding: "0 0 60px",
      }}
    >
      {/* NAV */}
      <div
        style={{
          maxWidth: 1120,
          margin: "0 auto",
          padding: "22px 32px 0",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#fff", fontWeight: 700, fontSize: 19 }}>
          <span style={{ filter: "brightness(0) invert(1)", display: "flex" }}>
            <BrandMark className="h-[26px] w-[26px]" />
          </span>
          ظهور
        </div>
        <div className="hidden md:flex" style={{ alignItems: "center", gap: 28, fontSize: 14, fontWeight: 600, color: "#fff" }}>
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} style={{ color: "#fff" }}>
              {l.label}
            </a>
          ))}
        </div>
        <button
          onClick={onOpenModal}
          style={{
            border: "1px solid rgba(255,255,255,0.7)",
            background: "rgba(255,255,255,0.16)",
            color: "#fff",
            fontSize: 13.5,
            fontWeight: 700,
            padding: "9px 22px",
            borderRadius: 24,
            whiteSpace: "nowrap",
            cursor: "pointer",
          }}
        >
          إنشاء حساب
        </button>
      </div>

      {/* HERO TEXT */}
      <div
        style={{
          maxWidth: 780,
          margin: "0 auto",
          padding: "74px 24px 0",
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 22,
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            background: "rgba(255,255,255,0.92)",
            border: "1px solid rgba(255,255,255,0.8)",
            borderRadius: 24,
            padding: "7px 18px",
            fontSize: 13,
            fontWeight: 600,
            color: "#0b8f86",
            whiteSpace: "nowrap",
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: TEAL_BRIGHT }} /> ظهور — تحليل ظهور
          العلامات التجارية
        </div>
        <h1 style={{ fontSize: 58, lineHeight: 1.15, letterSpacing: "-1px", fontWeight: 700, color: DARK, margin: 0 }}>
          حوّل محادثاتك إلى{" "}
          <span style={{ display: "inline-block", color: "#fff", transition: "opacity .35s ease", opacity: rotOn ? 1 : 0 }}>
            {rotWord}
          </span>
        </h1>
        <p style={{ fontSize: 16, color: MUTED2, maxWidth: 480, margin: 0, lineHeight: 1.8 }}>
          اعرف كيف تظهر علامتك، وحسّن حضورك لتتصدّر حيث يبحث عملاؤك بنقرة واحدة.
        </p>

        {/* Live domain -> /preview flow, unchanged from the previous homepage */}
        <form
          onSubmit={(e) => e.preventDefault()}
          style={{
            margin: 0,
            width: "100%",
            maxWidth: 500,
            display: "flex",
            gap: 7,
            padding: 7,
            border: "1px solid var(--line)",
            borderRadius: 9999,
            background: "var(--panel)",
            boxShadow: "0 8px 28px rgba(17,24,39,.09)",
          }}
        >
          <div
            dir="ltr"
            style={{
              flex: 1,
              minWidth: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-start",
              paddingInlineStart: 16,
            }}
          >
            <span className="mono" style={{ fontSize: 12.5, color: "var(--dim)" }}>
              https://
            </span>
            <input
              placeholder="example.com"
              dir="ltr"
              value={domain}
              onChange={(e) => onDomainChange(e.target.value)}
              style={{
                flex: 1,
                minWidth: 0,
                background: "transparent",
                border: 0,
                outline: "none",
                color: "var(--tx)",
                fontSize: 14.5,
                padding: "9px 0",
                textAlign: "left",
              }}
            />
          </div>
          <Link
            href={domain.trim() ? `/preview?domain=${encodeURIComponent(domain.trim())}` : "/preview"}
            className="rl-fill"
            style={{
              display: "inline-flex",
              alignItems: "center",
              border: 0,
              cursor: "pointer",
              background: "var(--tx)",
              color: "var(--btn-fg)",
              fontWeight: 600,
              fontSize: 14,
              padding: "11px 22px",
              borderRadius: 9999,
              whiteSpace: "nowrap",
            }}
          >
            ابدأ الآن
          </Link>
        </form>
      </div>

      {/* DASHBOARD MOCK */}
      <div
        style={{
          maxWidth: 1000,
          margin: "52px auto 0",
          background: "#fff",
          borderRadius: 20,
          border: "1px solid #eef3f2",
          boxShadow: "0 3px 8px rgba(4,43,41,0.05),0 48px 100px rgba(4,43,41,0.14)",
          overflow: "hidden",
        }}
      >
        {/* topbar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "11px 16px",
            borderBottom: "1px solid #f2f6f5",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, fontWeight: 700, fontSize: 12.5, color: DARK }}>
              <BrandMark className="h-[18px] w-[18px]" /> ظهور
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                background: "#f5f8f8",
                borderRadius: 16,
                padding: "5px 11px",
                fontSize: 10,
                color: "#9aabaa",
              }}
            >
              <span style={{ width: 10, height: 10, display: "block", flexShrink: 0 }}>
                <DashIcon name="search" color="#9aabaa" />
              </span>
              بحث
            </div>
            <span style={{ width: 13, height: 13, display: "block", flexShrink: 0 }}>
              <DashIcon name="bell" color="#7f9291" />
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 6, border: "1px solid #eef3f2", borderRadius: 16, padding: "4px 5px 4px 10px" }}>
              <div style={{ width: 17, height: 17, borderRadius: "50%", background: "#dfeceb" }} />
              <span style={{ fontSize: 10.5, fontWeight: 600, color: DARK }}>نورة العامر</span>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap" }}>
          {/* SIDEBAR */}
          <div
            className="hidden md:flex"
            style={{ width: 152, borderLeft: "1px solid #f2f6f5", padding: "12px 10px", flexDirection: "column", gap: 2 }}
          >
            {DASHBOARD_NAV_ITEMS.map((item) => (
              <div
                key={item.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 11.5,
                  fontWeight: 600,
                  padding: "5px 7px",
                  borderRadius: 9999,
                  background: item.active ? TEAL : "transparent",
                  color: item.active ? "#fff" : MUTED,
                }}
              >
                <span
                  style={{
                    width: 21,
                    height: 21,
                    borderRadius: "50%",
                    flexShrink: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: 4.5,
                    background: item.active ? "#fff" : "#f4f8f7",
                  }}
                >
                  <DashIcon name={item.icon} color={item.active ? TEAL : "#7f9291"} />
                </span>
                {item.label}
              </div>
            ))}
            <div style={{ marginTop: "auto", paddingTop: 16, textAlign: "center" }}>
              <div style={{ width: 34, height: 34, borderRadius: "50%", background: "#dfeceb", margin: "0 auto 6px" }} />
              <div style={{ fontSize: 10.5, fontWeight: 700, color: DARK }}>نورة العامر</div>
            </div>
          </div>

          {/* MAIN */}
          <div style={{ flex: 1, minWidth: 280, padding: 13, display: "flex", flexDirection: "column", gap: 11 }}>
            {/* QUICK STATS */}
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: 7 }}>
              <div style={{ flex: "0 0 92px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: DARK, letterSpacing: "-0.2px" }}>نظرة سريعة</div>
                <div style={{ fontSize: 9, color: "#9aabaa", marginTop: 4, lineHeight: 1.6 }}>آخر ٧ أيام</div>
              </div>
              {QUICK_STATS.map((s) => (
                <div
                  key={s.label}
                  style={{
                    position: "relative",
                    flex: "1 1 92px",
                    minWidth: 86,
                    background: "#fff",
                    border: `1px solid ${s.highlight ? "#cdeeea" : "#f1f5f4"}`,
                    borderRadius: 13,
                    padding: "11px 6px 10px",
                    textAlign: "center",
                    boxShadow: s.highlight ? "0 8px 20px rgba(11,158,148,0.16)" : "0 2px 5px rgba(4,43,41,0.035)",
                  }}
                >
                  <span
                    style={{
                      width: 26,
                      height: 26,
                      borderRadius: "50%",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 6.5,
                      marginBottom: 6,
                      background: s.highlight ? TEAL : "#f4f8f7",
                    }}
                  >
                    <DashIcon name={s.icon} color={s.highlight ? "#fff" : "#7f9291"} />
                  </span>
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center", gap: 4 }}>
                    <span style={{ fontSize: 16, fontWeight: 700, color: DARK, letterSpacing: "-0.2px" }}>{s.value}</span>
                    {s.delta && <span style={{ fontSize: 8.5, fontWeight: 700, color: GOOD_FG }}>{s.delta}</span>}
                  </div>
                  <div style={{ fontSize: 9.5, color: "#9aabaa", marginTop: 3, lineHeight: 1.45 }}>{s.label}</div>
                  {s.highlight && (
                    <span
                      style={{
                        position: "absolute",
                        bottom: -11,
                        left: "50%",
                        transform: "translateX(-50%)",
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        background: "#fff",
                        border: "1px solid #eef3f2",
                        boxShadow: "0 4px 10px rgba(4,43,41,0.12)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 10,
                        color: TEAL,
                      }}
                    >
                      ↗
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* TREND + AI ENGINES */}
            <div className="rl-zh-dash-2" style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 11 }}>
              <div style={{ border: "1px solid #f1f5f4", borderRadius: 12, padding: 13 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: DARK }}>تطوّر ظهورك</span>
                    {TREND_SERIES.map((s) => (
                      <span key={s.label} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 8.5, color: "#7f9291" }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.swatch, flexShrink: 0 }} />
                        {s.label}
                      </span>
                    ))}
                  </div>
                  <div style={{ display: "inline-flex", background: "#f5f8f8", borderRadius: 9999, padding: 2.5, gap: 2 }}>
                    {["الكل", "Google", "AI"].map((t, i) => (
                      <span
                        key={t}
                        style={{
                          fontSize: 8.5,
                          fontWeight: 700,
                          padding: "3px 9px",
                          borderRadius: 9999,
                          background: i === 0 ? "#fff" : "transparent",
                          color: i === 0 ? DARK : "#9aabaa",
                          boxShadow: i === 0 ? "0 1px 3px rgba(4,43,41,0.12)" : "none",
                        }}
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 6 }}>
                  <div
                    style={{
                      height: 108,
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      fontSize: 8.5,
                      color: "#c3cfce",
                      flexShrink: 0,
                    }}
                  >
                    {["80%", "60%", "40%", "20%", "0"].map((v) => (
                      <span key={v}>{v}</span>
                    ))}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ position: "relative", height: 108 }}>
                      {[0, 25, 50, 75, 100].map((t) => (
                        <span key={t} aria-hidden style={{ position: "absolute", left: 0, right: 0, top: `${t}%`, borderTop: "1px dashed #eef3f2" }} />
                      ))}
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "flex-end", gap: 3 }}>
                        {MONTHS.map((m, i) => (
                          <div key={m} style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 1.5 }}>
                            {TREND_SERIES.map((s) => (
                              <span
                                key={s.label}
                                style={{ width: 4, height: `${(s.values[i] / TREND_MAX) * 100}%`, background: s.bar, borderRadius: 2 }}
                              />
                            ))}
                          </div>
                        ))}
                      </div>
                      {/* pointer on أغس — the same "hovered bar" flourish the reference has */}
                      <span
                        aria-hidden
                        style={{
                          position: "absolute",
                          left: "37.5%",
                          top: "35%",
                          transform: "translate(-50%,-50%)",
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          background: TEAL,
                          border: "1.5px solid #fff",
                          boxShadow: "0 0 0 2px rgba(11,158,148,0.25)",
                        }}
                      />
                      <span
                        aria-hidden
                        style={{
                          position: "absolute",
                          left: "37.5%",
                          top: "35%",
                          transform: "translate(-50%,-165%)",
                          background: DARK,
                          color: "#fff",
                          fontSize: 8.5,
                          fontWeight: 700,
                          padding: "3px 7px",
                          borderRadius: 7,
                          whiteSpace: "nowrap",
                        }}
                      >
                        52%
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 3, marginTop: 6 }}>
                      {MONTHS.map((m) => (
                        <span key={m} style={{ flex: 1, textAlign: "center", fontSize: 8.5, color: "#a9b8b7" }}>
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ border: "1px solid #f1f5f4", borderRadius: 12, padding: 13, display: "flex", flexDirection: "column" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: DARK }}>محركات AI</div>
                  <span style={{ fontSize: 12, color: "#c3cfce", lineHeight: 1 }}>⋯</span>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-around" }}>
                  {AI_ENGINES.map((e) => (
                    <div key={e.name} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          width: 24,
                          height: 24,
                          borderRadius: 8,
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          padding: 5.5,
                          background: `${e.color}18`,
                        }}
                      >
                        <DashIcon name={e.icon} color={e.color} />
                      </span>
                      <span style={{ flex: 1, fontSize: 11.5, fontWeight: 600, color: DARK }}>{e.name}</span>
                      <span style={{ fontSize: 12.5, fontWeight: 700, color: DARK }}>{e.pct}%</span>
                      <span style={{ fontSize: 9.5, fontWeight: 700, color: e.up ? GOOD_FG : "#d9534f" }}>{e.up ? "↑" : "↓"}</span>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid #f4f8f7", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 9.5, color: "#9aabaa" }}>المتوسط</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: TEAL }}>53%</span>
                </div>
              </div>
            </div>

            {/* OPPORTUNITIES TABLE */}
            <div style={{ border: "1px solid #f1f5f4", borderRadius: 12, padding: 13 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: DARK }}>فرص التحسين</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ border: "1px solid #eef3f2", borderRadius: 9999, padding: "5px 11px", fontSize: 9.5, color: "#7f9291" }}>التأثير ⌄</span>
                  <span style={{ background: TEAL, color: "#fff", borderRadius: 9999, padding: "5px 13px", fontSize: 9.5, fontWeight: 700 }}>تصدير</span>
                </div>
              </div>
              <div style={{ overflowX: "auto" }}>
                <div style={{ minWidth: 520 }}>
                  <div style={{ display: "flex", gap: 8, fontSize: 8.5, color: "#a9b8b7", paddingBottom: 8, borderBottom: "1px solid #f4f8f7" }}>
                    <span style={{ flex: 1.5 }}>الفرصة</span>
                    <span style={{ flex: 1.5 }}>السبب</span>
                    <span style={{ flex: 0.7 }}>التأثير</span>
                    <span style={{ flex: 1.2 }}>المحرك</span>
                    <span style={{ flex: 1, textAlign: "left" }}>الإجراء</span>
                  </div>
                  {OPPORTUNITIES.map((o) => (
                    <div key={o.title} style={{ display: "flex", gap: 8, alignItems: "center", padding: "11px 0", borderBottom: "1px solid #f8fbfa" }}>
                      <span style={{ flex: 1.5, fontSize: 11, fontWeight: 600, color: DARK }}>{o.title}</span>
                      <span style={{ flex: 1.5, fontSize: 10.5, color: MUTED }}>{o.reason}</span>
                      <span style={{ flex: 0.7 }}>
                        <span style={{ background: "#fdf1e7", color: "#c07038", fontSize: 8.5, fontWeight: 700, padding: "2px 8px", borderRadius: 7 }}>{o.impact}</span>
                      </span>
                      <span style={{ flex: 1.2, fontSize: 10, color: MUTED }}>{o.engine}</span>
                      <span style={{ flex: 1, textAlign: "left" }}>
                        <span
                          style={{
                            display: "inline-block",
                            background: TEAL,
                            color: "#fff",
                            fontSize: 9,
                            fontWeight: 700,
                            padding: "5px 11px",
                            borderRadius: 9999,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {o.action}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* MARQUEE */}
      <div style={{ textAlign: "center", padding: "52px 0 0" }}>
        <div style={{ fontSize: 15.5, fontWeight: 600, color: "#33433f", marginBottom: 30 }}>شراكات مع نخبة من خبراء القطاع</div>
        <div
          style={{
            maxWidth: 1000,
            margin: "0 auto",
            overflow: "hidden",
            padding: "0 0 6px",
            WebkitMaskImage: "linear-gradient(to right, transparent, #000 12%, #000 88%, transparent)",
            maskImage: "linear-gradient(to right, transparent, #000 12%, #000 88%, transparent)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 64, width: "max-content", animation: "zuhoor-marquee 26s linear infinite" }}>
            {MARQUEE_LOGOS.map((logo, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, fontWeight: 700, fontSize: 17, color: "#0a2523", whiteSpace: "nowrap" }}>
                <span style={{ width: 20, height: 20, borderRadius: "50%", background: `linear-gradient(140deg,${TEAL_BRIGHT},${TEAL_DEEP})`, flexShrink: 0 }} />
                {logo}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function HowItWorks() {
  return (
    <div id="how">
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "96px 32px 0", textAlign: "center" }}>
        <SectionBadge label="كيف تعمل المنصة" />
        <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto", maxWidth: 640 }}>
          كيف يصنع تحليل الظهور فرقاً في نموّك
        </h2>
      </div>

      <div style={{ maxWidth: 1120, margin: "52px auto 0", padding: "0 32px", display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{ background: CARD_BG, borderRadius: 28, padding: "48px 40px", textAlign: "center" }}>
          <div
            style={{
              width: 46,
              height: 46,
              borderRadius: 13,
              background: "#fff",
              boxShadow: "0 6px 16px rgba(4,43,41,0.07)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 18px",
              color: TEAL,
              fontSize: 18,
            }}
          >
            ▦
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: DARK, letterSpacing: "-0.4px", marginBottom: 10 }}>رؤى لحظية</div>
          <p style={{ fontSize: 15, color: MUTED, maxWidth: 460, margin: "0 auto 34px", lineHeight: 1.8 }}>
            اطّلع على بيانات الإشارات لحظة حدوثها لتتخذ قرارات سريعة وتتفاعل مع تغيّرات السوق.
          </p>
          <div style={{ position: "relative", maxWidth: 720, margin: "0 auto" }}>
            <div
              className="rl-zh-liveinsight-card"
              style={{
                background: "#fff",
                borderRadius: 18,
                boxShadow: "0 3px 8px rgba(4,43,41,0.04),0 26px 60px rgba(4,43,41,0.09)",
                padding: "20px 20px 20px 150px",
                textAlign: "right",
              }}
            >
              <div style={{ fontSize: 13.5, fontWeight: 700, color: DARK, marginBottom: 18 }}>الظهور خلال السنة</div>
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 10, height: 110 }}>
                {BARS.map((bar, i) => (
                  <div key={i} style={{ flex: 1, display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 3, height: "100%" }}>
                    <div style={{ width: 8, height: `${bar.a}%`, background: "linear-gradient(180deg,#0bbfb1,#7fdcd4)", borderRadius: 4 }} />
                    <div style={{ width: 8, height: `${bar.b}%`, background: "linear-gradient(180deg,#79d8ce,#cdefeb)", borderRadius: 4 }} />
                  </div>
                ))}
              </div>
            </div>
            <div
              className="rl-zh-liveinsight-stat"
              style={{
                position: "absolute",
                left: -30,
                bottom: 34,
                background: "#fff",
                borderRadius: 14,
                boxShadow: "0 3px 8px rgba(4,43,41,0.06),0 20px 44px rgba(4,43,41,0.12)",
                padding: "14px 18px",
                textAlign: "right",
              }}
            >
              <div style={{ fontSize: 10.5, color: "#9aabaa", marginBottom: 4 }}>إجمالي الوصول</div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ fontSize: 19, fontWeight: 700, color: TEAL }}>٨٧٣٤٠٠</div>
                <div style={{ background: GOOD_BG, color: GOOD_FG, fontSize: 9.5, fontWeight: 700, padding: "3px 7px", borderRadius: 8 }}>+٤٫٥٪</div>
              </div>
            </div>
          </div>
        </div>

        <div className="rl-zh-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          <div style={{ background: CARD_BG, borderRadius: 28, padding: "40px 34px" }}>
            <div
              style={{
                width: 46,
                height: 46,
                borderRadius: 13,
                background: "#fff",
                boxShadow: "0 6px 16px rgba(4,43,41,0.07)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: 18,
                color: TEAL,
                fontSize: 18,
              }}
            >
              ◈
            </div>
            <div style={{ fontSize: 23, fontWeight: 700, color: DARK, marginBottom: 10 }}>مؤشر الظهور</div>
            <p style={{ fontSize: 14.5, color: MUTED, margin: "0 0 26px", lineHeight: 1.8 }}>
              يقيس الذكاء الاصطناعي كل إشارة حسب الوصول والانطباع لتعرف ما أحدث فرقاً فعلياً.
            </p>
            <div style={{ background: "#fff", borderRadius: 18, padding: 22, boxShadow: "0 3px 8px rgba(4,43,41,0.04),0 18px 44px rgba(4,43,41,0.07)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 20 }}>
                <div
                  style={{
                    width: 104,
                    height: 104,
                    borderRadius: "50%",
                    background: `conic-gradient(${TEAL} 0 76%, #e7f5f3 0)`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <div style={{ width: 74, height: 74, borderRadius: "50%", background: "#fff", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: DARK }}>٧٦</div>
                    <div style={{ fontSize: 9.5, color: "#9aabaa" }}>مؤشر الظهور</div>
                  </div>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
                  {SCORE_ROWS.map((s) => (
                    <div key={s.label}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: MUTED, marginBottom: 5 }}>
                        <span>{s.label}</span>
                        <span style={{ fontWeight: 700, color: DARK }}>{s.value}</span>
                      </div>
                      <div style={{ height: 6, borderRadius: 6, background: "#e7f5f3", overflow: "hidden" }}>
                        <div style={{ height: "100%", width: s.width, background: "linear-gradient(90deg,#0bbfb1,#7fdcd4)", borderRadius: 6 }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                {SPARKLINE.map((sp, i) => (
                  <div key={i} style={{ flex: 1, height: 34, display: "flex", alignItems: "flex-end" }}>
                    <div style={{ width: "100%", height: `${sp}%`, background: "#d6f0ec", borderRadius: 3 }} />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ background: CARD_BG, borderRadius: 28, padding: "40px 34px" }}>
            <div
              style={{
                width: 46,
                height: 46,
                borderRadius: 13,
                background: "#fff",
                boxShadow: "0 6px 16px rgba(4,43,41,0.07)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: 18,
                color: TEAL,
                fontSize: 18,
              }}
            >
              ⤢
            </div>
            <div style={{ fontSize: 23, fontWeight: 700, color: DARK, marginBottom: 10 }}>تقارير جاهزة للمشاركة</div>
            <p style={{ fontSize: 14.5, color: MUTED, margin: "0 0 26px", lineHeight: 1.8 }}>صدّر تقريراً واضحاً للإدارة أو العملاء بضغطة واحدة.</p>
            <div style={{ background: "#fff", borderRadius: 18, padding: 22, boxShadow: "0 3px 8px rgba(4,43,41,0.04),0 18px 44px rgba(4,43,41,0.07)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: DARK }}>تقرير الظهور — أغسطس</div>
                <div style={{ background: TEAL, color: "#fff", fontSize: 10.5, fontWeight: 700, padding: "6px 12px", borderRadius: 14 }}>تصدير PDF</div>
              </div>
              {REPORT_ROWS.map((r) => (
                <div key={r.title} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", borderBottom: "1px solid #f2f6f5" }}>
                  <span style={{ width: 26, height: 26, borderRadius: 8, background: "#eefaf8", color: TEAL, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, flexShrink: 0 }}>
                    {r.icon}
                  </span>
                  <span style={{ flex: 1, fontSize: 12.5, fontWeight: 600, color: DARK }}>{r.title}</span>
                  <span style={{ fontSize: 12, color: MUTED }}>{r.value}</span>
                  <span style={{ fontSize: 10.5, fontWeight: 700, color: GOOD_FG, background: GOOD_BG, padding: "3px 8px", borderRadius: 8 }}>{r.delta}</span>
                </div>
              ))}
              <div style={{ display: "flex", gap: 6, marginTop: 16, alignItems: "flex-end", height: 44 }}>
                {SPARKLINE.map((sp, i) => (
                  <div key={i} style={{ flex: 1, height: `${sp}%`, background: "linear-gradient(180deg,#0bbfb1,#cdefeb)", borderRadius: 3 }} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FeaturesSection() {
  return (
    <div id="features" style={{ maxWidth: 1120, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="الميزات" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 16px", maxWidth: 660 }}>
        كل ما تحتاجه لمتابعة علامتك التجارية
      </h2>
      <p style={{ fontSize: 15.5, color: MUTED, maxWidth: 480, margin: "0 auto 52px", lineHeight: 1.8 }}>
        تابع الإشارات، وقِس الظهور، وشارك النتائج مع فريقك وأصحاب المصلحة.
      </p>
      <div className="rl-zh-grid-3" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, textAlign: "right" }}>
        {FEATURES.map((f) => (
          <div key={f.title} style={{ border: `1px solid ${BORDER}`, borderRadius: 22, padding: 28, boxShadow: "0 2px 4px rgba(4,43,41,0.02),0 16px 40px rgba(4,43,41,0.04)" }}>
            <div style={{ width: 42, height: 42, borderRadius: 12, background: "#eefaf8", color: TEAL, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17, marginBottom: 18 }}>
              {f.icon}
            </div>
            <div style={{ fontSize: 18.5, fontWeight: 700, color: DARK, marginBottom: 8 }}>{f.title}</div>
            <div style={{ fontSize: 14, color: MUTED, lineHeight: 1.75 }}>{f.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TestimonialsSection() {
  return (
    <div id="testimonials" style={{ maxWidth: 1120, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="آراء العملاء" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 52px", maxWidth: 560 }}>
        فرق طموحة تثق بـظهور
      </h2>
      <div className="rl-zh-grid-3" style={{ display: "grid", gridTemplateColumns: "1.25fr 1fr 1fr", gap: 24, textAlign: "right" }}>
        <div
          style={{
            background: `linear-gradient(160deg,${TEAL_BRIGHT},${TEAL_DEEP})`,
            borderRadius: 24,
            padding: 32,
            color: "#fff",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            boxShadow: "0 24px 56px rgba(6,106,99,0.28)",
          }}
        >
          <div>
            <div style={{ color: "#bff2ec", fontSize: 13, marginBottom: 14 }}>★★★★★</div>
            <div style={{ fontSize: 17.5, lineHeight: 1.8 }}>
              منحتنا منصة ظهور وضوحاً وتنظيماً وسرعة. لأول مرة تقاريرنا عن الظهور جاهزة فعلاً للعرض على الإدارة.
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 32 }}>
            <div style={{ width: 38, height: 38, borderRadius: "50%", background: "rgba(255,255,255,0.25)" }} />
            <div style={{ fontSize: 13.5, lineHeight: 1.5 }}>
              <b>عامر الطالب</b>
              <div style={{ opacity: 0.75, fontSize: 12.5 }}>شركة كليماكور</div>
            </div>
          </div>
        </div>
        {TESTIMONIALS.map((t) => (
          <div
            key={t.name}
            style={{
              border: `1px solid ${BORDER}`,
              borderRadius: 24,
              padding: 28,
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              boxShadow: "0 2px 4px rgba(4,43,41,0.02),0 16px 40px rgba(4,43,41,0.04)",
            }}
          >
            <div>
              <div style={{ color: "#8fdcd4", fontSize: 12, marginBottom: 12 }}>★★★★★</div>
              <div style={{ fontSize: 14.5, color: "#33433f", lineHeight: 1.8 }}>{t.quote}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 26 }}>
              <div style={{ width: 34, height: 34, borderRadius: "50%", background: "#e8f2f1" }} />
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                <b style={{ color: DARK }}>{t.name}</b>
                <div style={{ color: "#8fa4a2", fontSize: 12 }}>{t.company}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PricingSection() {
  return (
    <div id="pricing" style={{ maxWidth: 1120, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="الأسعار" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 16px", maxWidth: 520 }}>
        أسعار واضحة تناسب كل فريق
      </h2>
      <p style={{ fontSize: 15.5, color: MUTED, maxWidth: 420, margin: "0 auto 30px", lineHeight: 1.8 }}>
        ابدأ بخطة صغيرة، وارتقِ عندما تتوسّع تغطية علامتك.
      </p>
      <div style={{ display: "inline-flex", background: "#f5f8f8", borderRadius: 26, padding: 5, gap: 4, marginBottom: 44 }}>
        <div style={{ background: TEAL, color: "#fff", fontSize: 13, fontWeight: 700, padding: "9px 24px", borderRadius: 22, whiteSpace: "nowrap" }}>شهري</div>
        <div style={{ color: MUTED, fontSize: 13, fontWeight: 700, padding: "9px 24px", whiteSpace: "nowrap" }}>سنوي · خصم ٣٠٪</div>
      </div>
      <div className="rl-zh-grid-3" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, textAlign: "right" }}>
        {PLANS.map((plan) => (
          <div key={plan.name} style={{ borderRadius: 24, padding: "32px 28px", display: "flex", flexDirection: "column", background: plan.bg, border: plan.border, boxShadow: plan.boxShadow }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: plan.nameColor, marginBottom: 10 }}>{plan.name}</div>
            <div style={{ fontSize: 38, fontWeight: 700, letterSpacing: "-0.8px", color: plan.priceColor }}>
              {plan.price}
              <span style={{ fontSize: 13.5, fontWeight: 600, color: plan.mutedColor, letterSpacing: 0 }}> ر.س / شهرياً</span>
            </div>
            <div style={{ fontSize: 14, color: plan.mutedColor, margin: "12px 0 26px", lineHeight: 1.75 }}>{plan.desc}</div>
            <div
              style={{
                textAlign: "center",
                fontSize: 13.5,
                fontWeight: 700,
                padding: 12,
                borderRadius: 24,
                marginBottom: 26,
                background: plan.btnBg,
                color: plan.btnColor,
                border: plan.btnBorder,
              }}
            >
              {plan.cta}
            </div>
            {plan.features.map((pf) => (
              <div key={pf} style={{ display: "flex", gap: 9, fontSize: 13.5, color: plan.featColor, padding: "6px 0" }}>
                <span style={{ color: plan.checkColor }}>✓</span>
                {pf}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function FaqSection() {
  return (
    <div id="faq" style={{ maxWidth: 820, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="الأسئلة الشائعة" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 44px" }}>
        لديك أسئلة؟ لدينا الإجابات
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, textAlign: "right" }}>
        {FAQS.map((q) => (
          <div
            key={q}
            style={{
              border: `1px solid ${BORDER}`,
              borderRadius: 18,
              padding: "20px 24px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 15,
              fontWeight: 600,
              color: DARK,
              boxShadow: "0 2px 4px rgba(4,43,41,0.02),0 12px 30px rgba(4,43,41,0.04)",
            }}
          >
            {q}
            <span style={{ width: 28, height: 28, borderRadius: "50%", background: "#eefaf8", color: TEAL, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0, marginRight: 16 }}>
              +
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CtaBanner({ onOpenModal }: { onOpenModal: () => void }) {
  return (
    <div style={{ maxWidth: 1120, margin: "104px auto 0", padding: "0 32px" }}>
      <div
        style={{
          background: `radial-gradient(120% 140% at 50% 0%, ${TEAL_BRIGHT} 0%, #0ab3a6 45%, ${TEAL_DEEP} 100%)`,
          borderRadius: 32,
          padding: "72px 40px",
          textAlign: "center",
          color: "#fff",
          boxShadow: "0 30px 70px rgba(6,106,99,0.3)",
        }}
      >
        <h2 style={{ fontSize: 38, lineHeight: 1.3, letterSpacing: "-0.6px", fontWeight: 700, margin: "0 auto 14px", maxWidth: 560 }}>
          اعرف كل ظهور لعلامتك التجارية
        </h2>
        <p style={{ fontSize: 15.5, color: "#dcf6f3", maxWidth: 440, margin: "0 auto 30px", lineHeight: 1.8 }}>
          جهّز المتابعة في دقائق، وشارك أول تقرير ظهور اليوم.
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
          <Link
            href="/preview"
            style={{ background: "#fff", color: TEAL_DEEP, fontSize: 14, fontWeight: 700, padding: "13px 32px", borderRadius: 26, whiteSpace: "nowrap" }}
          >
            ابدأ الآن
          </Link>
          <button
            onClick={onOpenModal}
            style={{
              border: "1px solid rgba(255,255,255,0.55)",
              color: "#fff",
              background: "transparent",
              fontSize: 14,
              fontWeight: 700,
              padding: "13px 30px",
              borderRadius: 26,
              whiteSpace: "nowrap",
              cursor: "pointer",
            }}
          >
            احجز عرضاً توضيحياً
          </button>
        </div>
      </div>
    </div>
  );
}

function SiteFooter() {
  return (
    <footer id="footer">
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "56px 32px 40px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 28 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700, fontSize: 17, color: DARK }}>
            <BrandMark className="h-[26px] w-[26px]" /> ظهور
          </div>
          <div style={{ display: "flex", gap: 20, fontSize: 13.5, color: MUTED, fontWeight: 600, flexWrap: "wrap" }}>
            <a href="#" style={{ color: MUTED }}>المنصة</a>
            <a href="#pricing" style={{ color: MUTED }}>الأسعار</a>
            <a href="#" style={{ color: MUTED }}>المدونة</a>
            <a href="#" style={{ color: MUTED }}>تواصل</a>
            <a href="#" style={{ color: MUTED }}>الخصوصية</a>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 11, background: "#eefaf8", color: TEAL, display: "flex", alignItems: "center", justifyContent: "center" }}>📷</div>
          <div style={{ width: 36, height: 36, borderRadius: 11, background: "#eefaf8", color: TEAL, display: "flex", alignItems: "center", justifyContent: "center" }}>𝕏</div>
          <div style={{ width: 36, height: 36, borderRadius: 11, background: "#eefaf8", color: TEAL, display: "flex", alignItems: "center", justifyContent: "center" }}>in</div>
        </div>
      </div>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "0 32px 44px", fontSize: 13, color: "#8fa4a2", borderTop: `1px solid #f2f6f5` }}>
        <div style={{ paddingTop: 22 }}>© ٢٠٢٦ ظهور. جميع الحقوق محفوظة.</div>
      </div>
    </footer>
  );
}

function JoinModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [interest, setInterest] = useState("");
  const [usage, setUsage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const close = () => {
    if (submitting) return;
    onClose();
    setStep(0);
    setName("");
    setEmail("");
    setInterest("");
    setUsage("");
    setSubmitted(false);
    setError(null);
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await joinBetaDirectly({ name, email, report_feedback: interest, interest_level: usage });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذّر إرسال الطلب");
    } finally {
      setSubmitting(false);
    }
  };

  const fieldLabel: CSSProperties = { marginTop: 16, fontSize: 13, fontWeight: 600 };
  const textInput: CSSProperties = {
    marginTop: 8,
    width: "100%",
    background: "var(--panel)",
    border: "1px solid var(--line)",
    borderRadius: 11,
    outline: "none",
    color: "var(--tx)",
    fontSize: 14,
    padding: "12px 14px",
  };
  const nextBtn: CSSProperties = {
    marginTop: 22,
    width: "100%",
    border: 0,
    cursor: "pointer",
    background: "var(--tx)",
    color: "var(--btn-fg)",
    fontWeight: 600,
    fontSize: 14,
    padding: 13,
    borderRadius: 11,
  };
  const optionRow = (checked: boolean): CSSProperties => ({
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 12.5,
    cursor: "pointer",
    padding: "9px 10px",
    borderRadius: 9,
    border: "1px solid var(--line)",
    background: checked ? "var(--panel2)" : "transparent",
  });

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="rasid-landing"
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20, zIndex: 60 }}
      onClick={close}
    >
      <div
        dir="rtl"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 20,
          width: "100%",
          maxWidth: 420,
          maxHeight: "85vh",
          padding: "22px 24px 24px",
          display: "flex",
          flexDirection: "column",
          overflowY: "auto",
          textAlign: "right",
        }}
      >
        {submitted ? (
          <>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>تم! وصلنا طلبك</h2>
            <p style={{ margin: "12px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>راح نتواصل معك قريبًا لتفعيل نسختك التجريبية</p>
            <button onClick={close} className="rl-fill-soft" style={{ ...nextBtn }}>
              تمام
            </button>
          </>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>إنشاء حساب</h2>
              <span className="mono" style={{ fontSize: 11, color: "var(--dim)" }}>{step + 1}/3</span>
            </div>

            {step === 0 && (
              <>
                <div style={fieldLabel}>الاسم</div>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="اسمك" style={textInput} />
                <div style={fieldLabel}>البريد الإلكتروني</div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  dir="ltr"
                  style={{ ...textInput, textAlign: "left" }}
                />
                <button
                  onClick={() => setStep(1)}
                  disabled={!name.trim() || !email.trim()}
                  className="rl-fill-soft"
                  style={{ ...nextBtn, opacity: !name.trim() || !email.trim() ? 0.6 : 1 }}
                >
                  التالي
                </button>
              </>
            )}

            {step === 1 && (
              <>
                <div style={fieldLabel}>وش يشدك أكثر بظهور؟</div>
                <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  {JOIN_INTEREST_OPTIONS.map((opt) => (
                    <label key={opt.value} style={optionRow(interest === opt.value)}>
                      <input
                        type="radio"
                        name="join_interest"
                        value={opt.value}
                        checked={interest === opt.value}
                        onChange={() => setInterest(opt.value)}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
                <button onClick={() => setStep(2)} disabled={!interest} className="rl-fill-soft" style={{ ...nextBtn, opacity: !interest ? 0.6 : 1 }}>
                  التالي
                </button>
              </>
            )}

            {step === 2 && (
              <>
                <div style={fieldLabel}>قد إيش مهتم تستخدم ظهور لمتابعة علامتك؟</div>
                <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  {JOIN_USAGE_OPTIONS.map((opt) => (
                    <label key={opt.value} style={optionRow(usage === opt.value)}>
                      <input type="radio" name="join_usage" value={opt.value} checked={usage === opt.value} onChange={() => setUsage(opt.value)} />
                      {opt.label}
                    </label>
                  ))}
                </div>
                {error && <div style={{ marginTop: 10, fontSize: 12.5, color: "#dc4c4c" }}>{error}</div>}
                <button onClick={submit} disabled={!usage || submitting} className="rl-fill-soft" style={{ ...nextBtn, opacity: !usage || submitting ? 0.6 : 1 }}>
                  {submitting ? "جاري الإرسال..." : "تم"}
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
