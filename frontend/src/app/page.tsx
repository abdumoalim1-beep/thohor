"use client";

import Link from "next/link";
import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

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
// Tint behind the white rows inside each "كيف تبدأ" step card.
const STEP_PANEL = "#f4faf9";

const WORDS = ["إيرادات", "أرباح", "عملاء"];

const NAV_LINKS: { label: string; href: string }[] = [
  { label: "المميزات", href: "#features" },
  { label: "كيف تعمل", href: "#steps" },
  { label: "التسعير", href: "#pricing" },
  { label: "الأسئلة الشائعة", href: "#faq" },
];

const DASHBOARD_NAV_ITEMS: { icon: DashIconName; label: string; active?: boolean }[] = [
  { icon: "home", label: "لوحة التحكم", active: true },
  { icon: "trend", label: "النمو" },
  { icon: "audience", label: "الجمهور" },
  { icon: "signal", label: "الإشارات" },
  { icon: "columns", label: "المنافسون" },
  { icon: "doc", label: "التقارير" },
  { icon: "alert", label: "التنبيهات" },
  { icon: "gear", label: "الإعدادات" },
];

const QUICK_STATS: { icon: DashIconName; value: string; label: string }[] = [
  { icon: "target", value: "873 ألف", label: "الوصول الشهري" },
  { icon: "signal", value: "124970", label: "إجمالي الإشارات" },
  { icon: "triangle", value: "80%", label: "نسبة الإيجابية" },
  { icon: "doc", value: "320 ألف", label: "وصول الأخبار" },
  { icon: "spark", value: "48", label: "حملات نشطة" },
  { icon: "alert", value: "12", label: "تنبيهات سلبية" },
];

const BAR_A = [38, 54, 42, 66, 58, 80, 62, 88, 70, 96, 76, 92];
const BAR_B = [22, 40, 30, 48, 36, 58, 44, 66, 50, 72, 54, 68];
const BARS = BAR_A.map((a, i) => ({ a, b: BAR_B[i] }));
const MONTHS = ["ينا", "فبر", "مار", "أبر", "ماي", "يون", "يول", "أغس", "سبت", "أكت", "نوف", "ديس"];

// Two-series year chart. Values are "in hundreds" so the axis reads
// 2/4/6/8 ألف, and أغس lands on 64 -> the 6400 tooltip.
const CHART_MAX = 80;
const CHART_SERIES: { label: string; color: string; values: number[] }[] = [
  { label: "الإشارات", color: "#0d9e88", values: [40, 78, 46, 56, 52, 70, 48, 64, 44, 72, 54, 66] },
  { label: "الوصول", color: "#a9e2d7", values: [26, 62, 34, 44, 38, 58, 36, 50, 32, 60, 42, 52] },
];

const APPROVALS: { icon: DashIconName; name: string; date: string }[] = [
  { icon: "doc", name: "الأخبار والصحافة", date: "10 يونيو 03:20" },
  { icon: "audience", name: "التواصل الاجتماعي", date: "12 يونيو 04:30" },
  { icon: "signal", name: "البودكاست", date: "14 يونيو 05:40" },
];

const MENTIONS: { title: string; icon: DashIconName; channel: string; source: string; status: string; ended?: boolean; date: string }[] = [
  { title: "تقرير أداء الحملة", icon: "doc", channel: "الأخبار", source: "الرياض", status: "قيد المراجعة", date: "10 يونيو 03:20" },
  { title: "ذكر العلامة في مقابلة", icon: "signal", channel: "بودكاست", source: "جدة", status: "نشط", date: "08 يونيو 04:30" },
  { title: "حملة الوعي الرقمي", icon: "audience", channel: "اجتماعي", source: "الدمام", status: "منتهي", ended: true, date: "02 فبراير 05:40" },
];

const MARQUEE_BASE = ["شعار", "منصة", "مجموعة", "شركة", "مؤسسة", "استوديو", "مختبر", "وكالة"];
const MARQUEE_LOGOS = [...MARQUEE_BASE, ...MARQUEE_BASE];

const SCORE_ROWS: { label: string; value: string; width: string }[] = [
  { label: "الوصول", value: "82%", width: "82%" },
  { label: "الانطباع الإيجابي", value: "74%", width: "74%" },
  { label: "حصة الصوت", value: "61%", width: "61%" },
];

const SPARKLINE = [42, 66, 54, 78, 60, 88, 70, 96, 74, 90];

const REPORT_ROWS: { icon: string; title: string; value: string; delta: string }[] = [
  { icon: "📰", title: "الأخبار والصحافة", value: "4826 إشارة", delta: "+12%" },
  { icon: "📱", title: "التواصل الاجتماعي", value: "12904 إشارة", delta: "+8%" },
  { icon: "🎙", title: "البودكاست", value: "318 إشارة", delta: "+5%" },
  { icon: "📺", title: "الفيديو", value: "1240 إشارة", delta: "+9%" },
];

const STEP_1_ROWS: { label: string; value: string; icon: DashIconName; pending?: boolean }[] = [
  { label: "صفحات الموقع", value: "248 صفحة", icon: "doc" },
  { label: "نشاطك وسوقك", value: "مُحدّد", icon: "target" },
  { label: "ربط Google", value: "جاري", icon: "signal", pending: true },
];

const STEP_2_STATS: { label: string; display: string; pct: number }[] = [
  { label: "الظهور في Google", display: "62%", pct: 62 },
  { label: "محركات الذكاء", display: "41%", pct: 41 },
];

const STEP_2_ISSUES: { label: string; impact: string; color: string; bg: string }[] = [
  { label: "صفحات مهمة غير مفهرسة", impact: "عالي", color: "#d9605a", bg: "#fdeceb" },
  { label: "وصف وعناوين ناقصة", impact: "متوسط", color: "#cf9235", bg: "#fdf3e5" },
];

const STEP_3_FIXES: { label: string; status: string; done?: boolean }[] = [
  { label: "إضافة وصف للصفحات الرئيسية", status: "تطبيق" },
  { label: "إصلاح فهرسة صفحة الخدمات", status: "تم ✓", done: true },
];

// Chronological, so index 0 (ينا) renders rightmost under RTL and the
// curve climbs leftward toward أكت — i.e. upward as time advances.
const STEP_3_TREND = [24, 30, 38, 44, 52, 57, 66, 74, 79];
const STEP_3_MONTHS = ["ينا", "أبر", "يول", "أكت"];

const TESTIMONIALS: { quote: string; company: string }[] = [
  {
    quote: "ظهور اختصر علينا ساعات من التحليل والمتابعة وجمع لنا الصورة كاملة من الظهور إلى فرص التحسين في مكان واحد",
    company: "وكالة Trigger",
  },
  { quote: "ظهور كشف لنا فرصًا ما كنا نشوفها والأهم أنه وضّح لنا وش نغيّر ووش نبدأ فيه", company: "شركة راصد" },
  {
    quote: "صار عندنا تصور أوضح عن ظهورنا ومنافسينا وما يحتاجه الموقع للتحسن بدل الاعتماد على التخمين",
    company: "منصة بوصلة",
  },
];

type PricingPlan = {
  name: string;
  badge?: string;
  oldPrice?: string;
  price: string;
  period?: string;
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

// The 50% launch discount is stated once, on the toggle above the cards —
// the struck-through original price carries it per card without repeating
// the wording three more times.
const PLANS: PricingPlan[] = [
  {
    ...PLAN_LIGHT,
    name: "البداية",
    oldPrice: "250 ر.س",
    price: "125",
    period: " ر.س / شهريًا",
    desc: "لبداية قوية في Google ومحركات الذكاء الاصطناعي",
    cta: "ابدأ الآن",
    features: [
      "موقع واحد",
      "Google وChatGPT وGemini وPerplexity",
      "25 سؤالًا للمتابعة",
      "تحليل حتى 500 صفحة",
      "متابعة 3 منافسين",
      "اكتشاف فرص التحسين",
      "تحسينات بنقرة واحدة",
      "تحديث أسبوعي",
    ],
  },
  {
    name: "النمو",
    badge: "الأكثر اختيارًا",
    oldPrice: "598 ر.س",
    price: "299",
    period: " ر.س / شهريًا",
    desc: "للمواقع التي تريد تحسين ظهورها بشكل مستمر",
    cta: "ابدأ مع النمو",
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
    features: [
      "كل ما في البداية",
      "100 سؤال للمتابعة",
      "تحليل حتى 2,000 صفحة",
      "متابعة 10 منافسين",
      "تحديث يومي للظهور",
      "تحسين الصفحات والمحتوى والصور",
      "إنشاء صفحات ومحتوى عند الحاجة",
      "فرص تحسين أكثر",
    ],
  },
  {
    ...PLAN_LIGHT,
    name: "الأعمال",
    price: "تواصل معنا",
    desc: "للشركات والوكالات ذات الاحتياجات الأكبر",
    cta: "تواصل معنا",
    features: [
      "كل ما في النمو",
      "مواقع متعددة",
      "حدود متابعة مخصصة",
      "زحف وتحليل مخصص",
      "عدد أكبر من المنافسين",
      "أعضاء فريق متعددون",
      "API وتكاملات",
      "دعم وإعداد مخصص",
    ],
  },
];

const FAQS: [string, string][] = [
  [
    "كيف يعرف ظهور ما الذي يحتاجه موقعي للتحسين؟",
    "يحلل ظهور موقعك ومنافسيك ويفحص صفحات موقعك ليحدد المشاكل والفرص الأكثر تأثيرًا على ظهورك",
  ],
  [
    "ما التحسينات التي يستطيع ظهور تنفيذها على موقعي؟",
    "يحدد ظهور التحسين المناسب حسب احتياج موقعك من تحسين الصفحات والمحتوى والصور والعناصر التقنية إلى إنشاء صفحات ومحتوى جديد عند الحاجة",
  ],
  [
    "هل يتابع ظهور موقعي في Google ومحركات الذكاء الاصطناعي؟",
    "نعم يتابع ظهورك ومنافسيك في Google وChatGPT وGemini وPerplexity لتعرف أين تظهر وأين تحتاج للتحسين",
  ],
  [
    "هل أحتاج خبرة في SEO أو البرمجة لاستخدام ظهور؟",
    "لا يحول ظهور التحليل إلى خطوات واضحة وتحسينات قابلة للتنفيذ دون الحاجة إلى خبرة تقنية",
  ],
  [
    "كيف أربط موقعي بظهور وأبدأ التحسين؟",
    "اربط موقعك بظهور عبر إضافة رابط بسيط إلى موقعك ثم اربط Google Analytics وبعدها يبدأ ظهور بتحليل موقعك ويمكنك تطبيق التحسينات المقترحة مباشرة بضغطة زر",
  ],
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
      <PlatformFeatures />
      <HowStepsSection />
      <TestimonialsSection />
      <PricingSection onOpenModal={() => setModalOpen(true)} />
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
  | "home"
  | "trend"
  | "audience"
  | "signal"
  | "columns"
  | "doc"
  | "alert"
  | "gear"
  | "target"
  | "triangle"
  | "spark";

// Line icons for the hero's product mock, drawn to match the glyph
// shapes in the approved dashboard design (home / arrow / concentric
// circle / diamond / split panes / document / bang / gear / rings /
// triangle / four-point star).
function DashIcon({ name, color = "currentColor" }: { name: DashIconName; color?: string }) {
  const c = { width: "100%", height: "100%", viewBox: "0 0 24 24", fill: "none" as const };
  const s = { stroke: color, strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "home":
      return (
        <svg {...c}>
          <path d="M3.8 10.4L12 3.6l8.2 6.8v9.1a1 1 0 01-1 1H4.8a1 1 0 01-1-1z" {...s} />
        </svg>
      );
    case "trend":
      return (
        <svg {...c}>
          <path d="M4.5 18.5L10 12.4l3.6 3.3 6-7.4" {...s} />
          <path d="M15.6 8.3h4v4" {...s} />
        </svg>
      );
    case "audience":
      return (
        <svg {...c}>
          <circle cx="12" cy="12" r="8.2" {...s} />
          <circle cx="12" cy="12" r="3.1" fill={color} stroke="none" />
        </svg>
      );
    case "signal":
      return (
        <svg {...c}>
          <path d="M12 3.4l8.6 8.6-8.6 8.6L3.4 12z" {...s} />
          <circle cx="12" cy="12" r="2.2" fill={color} stroke="none" />
        </svg>
      );
    case "columns":
      return (
        <svg {...c}>
          <rect x="3.6" y="4.2" width="16.8" height="15.6" rx="2.6" {...s} />
          <path d="M12 4.2v15.6" {...s} />
        </svg>
      );
    case "doc":
      return (
        <svg {...c}>
          <rect x="4.4" y="3.6" width="15.2" height="16.8" rx="2.6" {...s} />
          <path d="M8.2 8.4h7.6M8.2 12h7.6M8.2 15.6h4.6" {...s} />
        </svg>
      );
    case "alert":
      return (
        <svg {...c}>
          <path d="M12 7.4v5.4" {...s} />
          <circle cx="12" cy="16.6" r="1.15" fill={color} stroke="none" />
        </svg>
      );
    case "gear":
      return (
        <svg {...c}>
          <circle cx="12" cy="12" r="3" {...s} />
          <path d="M12 2.9v2.4M12 18.7v2.4M21.1 12h-2.4M5.3 12H2.9M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7M18.4 18.4l-1.7-1.7M7.3 7.3L5.6 5.6" {...s} />
        </svg>
      );
    case "target":
      return (
        <svg {...c}>
          <circle cx="12" cy="12" r="8.2" {...s} />
          <circle cx="12" cy="12" r="3.6" {...s} />
        </svg>
      );
    case "triangle":
      return (
        <svg {...c}>
          <path d="M12 4.6l8 13.4H4z" {...s} />
        </svg>
      );
    case "spark":
      return (
        <svg {...c}>
          <path d="M12 3.2l2.1 6.7 6.7 2.1-6.7 2.1L12 20.8l-2.1-6.7L3.2 12l6.7-2.1z" {...s} />
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
        <a href="#top" style={{ display: "flex", alignItems: "center", gap: 10, color: "#fff", fontWeight: 700, fontSize: 19 }}>
          <span style={{ filter: "brightness(0) invert(1)", display: "flex" }}>
            <BrandMark className="h-[26px] w-[26px]" />
          </span>
          ظهور
        </a>
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
          borderRadius: 24,
          boxShadow: "0 3px 8px rgba(4,43,41,0.05),0 48px 100px rgba(4,43,41,0.14)",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap" }}>
          {/* SIDEBAR — first child, so RTL puts it on the right like the design */}
          <div
            className="hidden md:flex"
            style={{
              width: 194,
              flexDirection: "column",
              background: "#fff",
              borderLeft: "1px solid #eef4f3",
              padding: "20px 14px 18px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 9, fontWeight: 700, fontSize: 17, color: DARK, padding: "0 6px 20px" }}>
              <BrandMark className="h-[22px] w-[22px]" /> ظهور
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {DASHBOARD_NAV_ITEMS.map((item) => (
                <div
                  key={item.label}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: 12,
                    fontWeight: 600,
                    padding: "7px 9px",
                    borderRadius: 9999,
                    background: item.active ? TEAL : "transparent",
                    color: item.active ? "#fff" : "#556663",
                  }}
                >
                  <span
                    style={{
                      width: 25,
                      height: 25,
                      borderRadius: "50%",
                      flexShrink: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 5.5,
                      background: item.active ? "#fff" : "#eaf6f3",
                    }}
                  >
                    <DashIcon name={item.icon} color={item.active ? TEAL : "#4d8f85"} />
                  </span>
                  {item.label}
                </div>
              ))}
            </div>

            <div style={{ marginTop: "auto", paddingTop: 24, textAlign: "center" }}>
              <div style={{ position: "relative", width: 40, height: 40, margin: "0 auto 8px" }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    background: "#eaf6f3",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 15,
                    fontWeight: 700,
                    color: "#4d8f85",
                  }}
                >
                  ن
                </div>
                <span
                  style={{
                    position: "absolute",
                    top: -3,
                    left: -3,
                    minWidth: 17,
                    height: 17,
                    borderRadius: 9999,
                    background: TEAL,
                    color: "#fff",
                    fontSize: 9,
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: "2px solid #fff",
                  }}
                >
                  9
                </span>
              </div>
              <div style={{ fontSize: 11.5, fontWeight: 700, color: DARK }}>نورة العامر</div>
              <div style={{ fontSize: 9, color: "#a9b8b7", marginTop: 3 }}>noura@zuhoor.sa</div>
            </div>
          </div>

          {/* MAIN */}
          <div style={{ flex: 1, minWidth: 280, background: "#f7fbfa", padding: 16, display: "flex", flexDirection: "column", gap: 13 }}>
            {/* QUICK STATS */}
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: 8 }}>
              <div style={{ flex: "0 0 108px", display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 2px" }}>
                <div style={{ fontSize: 14.5, fontWeight: 700, color: DARK, letterSpacing: "-0.2px" }}>مؤشرات سريعة</div>
                <div style={{ fontSize: 9.5, color: "#9aabaa", marginTop: 6, lineHeight: 1.65 }}>قياس الظهور خلال آخر 7 أيام</div>
              </div>
              {QUICK_STATS.map((s) => (
                <div
                  key={s.label}
                  style={{
                    flex: "1 1 86px",
                    minWidth: 80,
                    background: "#fff",
                    borderRadius: 16,
                    padding: "13px 6px 12px",
                    textAlign: "center",
                    boxShadow: "0 1px 3px rgba(4,43,41,0.04),0 8px 20px rgba(4,43,41,0.045)",
                  }}
                >
                  <span
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 7,
                      marginBottom: 9,
                      background: "#eaf6f3",
                    }}
                  >
                    <DashIcon name={s.icon} color="#4d8f85" />
                  </span>
                  <div style={{ fontSize: 14, fontWeight: 700, color: DARK, letterSpacing: "-0.2px" }}>{s.value}</div>
                  <div style={{ fontSize: 9, color: "#9aabaa", marginTop: 4, lineHeight: 1.45 }}>{s.label}</div>
                </div>
              ))}
            </div>

            {/* CHART + APPROVALS */}
            <div className="rl-zh-dash-2" style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 13 }}>
              <div style={{ background: "#fff", borderRadius: 18, padding: 16, boxShadow: "0 1px 3px rgba(4,43,41,0.04),0 8px 20px rgba(4,43,41,0.045)" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: DARK }}>الظهور خلال السنة</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
                    {CHART_SERIES.map((s) => (
                      <span key={s.label} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 9.5, color: "#7f9291" }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
                        {s.label}
                      </span>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ position: "relative", height: 122 }}>
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "flex-end", gap: 4 }}>
                        {MONTHS.map((m, i) => (
                          <div key={m} style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 2 }}>
                            {CHART_SERIES.map((s) => (
                              <span key={s.label} style={{ width: 6, height: `${(s.values[i] / CHART_MAX) * 100}%`, background: s.color, borderRadius: 3 }} />
                            ))}
                          </div>
                        ))}
                      </div>
                      {/* أغس sits at 64 — the tooltip the design shows */}
                      <span
                        aria-hidden
                        style={{
                          position: "absolute",
                          left: "37.5%",
                          top: "20%",
                          transform: "translate(-50%,-100%)",
                          background: DARK,
                          color: "#fff",
                          fontSize: 9.5,
                          fontWeight: 700,
                          padding: "4px 9px",
                          borderRadius: 8,
                          whiteSpace: "nowrap",
                        }}
                      >
                        6400
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 4, marginTop: 8 }}>
                      {MONTHS.map((m) => (
                        <span key={m} style={{ flex: 1, textAlign: "center", fontSize: 8.5, color: "#a9b8b7" }}>
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div
                    style={{
                      height: 122,
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      fontSize: 8.5,
                      color: "#b9c7c5",
                      flexShrink: 0,
                      borderRight: "1px dashed #e9f2f0",
                      paddingRight: 7,
                    }}
                  >
                    {["8 ألف", "6 ألف", "4 ألف", "2 ألف", "0"].map((v) => (
                      <span key={v}>{v}</span>
                    ))}
                  </div>
                </div>
              </div>

              <div style={{ background: "#fff", borderRadius: 18, padding: 16, boxShadow: "0 1px 3px rgba(4,43,41,0.04),0 8px 20px rgba(4,43,41,0.045)", display: "flex", flexDirection: "column" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: DARK }}>بانتظار المراجعة</div>
                  <span
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: "50%",
                      background: "#f2f8f7",
                      color: "#9aabaa",
                      fontSize: 12,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      lineHeight: 1,
                    }}
                  >
                    ⋯
                  </span>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-around", gap: 4 }}>
                  {APPROVALS.map((a) => (
                    <div key={a.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span
                        style={{
                          width: 30,
                          height: 30,
                          borderRadius: "50%",
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          padding: 7,
                          background: "#eaf6f3",
                        }}
                      >
                        <DashIcon name={a.icon} color="#4d8f85" />
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 11.5, fontWeight: 700, color: DARK }}>{a.name}</div>
                        <div style={{ fontSize: 9, color: "#a9b8b7", marginTop: 3 }}>{a.date}</div>
                      </div>
                      <span
                        style={{
                          border: "1px solid #e3efec",
                          borderRadius: 9999,
                          padding: "5px 11px",
                          fontSize: 9,
                          color: "#7f9291",
                          whiteSpace: "nowrap",
                          flexShrink: 0,
                        }}
                      >
                        قيد المراجعة
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* MENTIONS TABLE */}
            <div style={{ background: "#fff", borderRadius: 18, padding: 16, boxShadow: "0 1px 3px rgba(4,43,41,0.04),0 8px 20px rgba(4,43,41,0.045)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: DARK }}>إدارة الإشارات</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ border: "1px solid #e3efec", borderRadius: 9999, padding: "6px 13px", fontSize: 9.5, color: "#7f9291" }}>الحالة ⌄</span>
                  <span style={{ background: TEAL, color: "#fff", borderRadius: 9999, padding: "6px 15px", fontSize: 9.5, fontWeight: 700 }}>تصدير ⬇</span>
                </div>
              </div>
              <div style={{ overflowX: "auto" }}>
                <div style={{ minWidth: 560 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 9, color: "#a9b8b7", padding: "0 12px 10px" }}>
                    <span style={{ flex: "0 0 15px" }} />
                    <span style={{ flex: 1.7 }}>الإشارة</span>
                    <span style={{ flex: 1.1 }}>القناة</span>
                    <span style={{ flex: 0.9 }}>المصدر</span>
                    <span style={{ flex: 1 }}>الحالة</span>
                    <span style={{ flex: 1.2 }}>التاريخ</span>
                    <span style={{ flex: "0 0 14px" }} />
                  </div>
                  {MENTIONS.map((m) => (
                    <div
                      key={m.title}
                      style={{
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                        background: "#f6faf9",
                        borderRadius: 13,
                        padding: "11px 12px",
                        marginBottom: 8,
                      }}
                    >
                      <span style={{ flex: "0 0 15px", width: 15, height: 15, borderRadius: 5, border: "1.5px solid #d7e6e3", background: "#fff" }} />
                      <span style={{ flex: 1.7, fontSize: 11, fontWeight: 700, color: DARK }}>{m.title}</span>
                      <span style={{ flex: 1.1, display: "flex", alignItems: "center", gap: 7, fontSize: 10.5, color: MUTED }}>
                        <span
                          style={{
                            width: 22,
                            height: 22,
                            borderRadius: "50%",
                            flexShrink: 0,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            padding: 5,
                            background: "#fff",
                          }}
                        >
                          <DashIcon name={m.icon} color="#4d8f85" />
                        </span>
                        {m.channel}
                      </span>
                      <span style={{ flex: 0.9, fontSize: 10.5, color: MUTED }}>{m.source}</span>
                      <span style={{ flex: 1 }}>
                        <span
                          style={{
                            display: "inline-block",
                            background: m.ended ? "#eef2f1" : "#ddf3ee",
                            color: m.ended ? "#8a9997" : "#0b8f7d",
                            fontSize: 9,
                            fontWeight: 700,
                            padding: "4px 10px",
                            borderRadius: 9999,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {m.status}
                        </span>
                      </span>
                      <span style={{ flex: 1.2, fontSize: 10, color: MUTED, whiteSpace: "nowrap" }}>{m.date}</span>
                      <span style={{ flex: "0 0 14px", fontSize: 11, color: "#c3cfce", textAlign: "left", lineHeight: 1 }}>⋯</span>
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

function PlatformFeatures() {
  return (
    // Bottom padding is load-bearing: every other section on this page
    // relies on the *next* one's top padding for separation, which works
    // only while they share a background. The steps section that follows
    // paints its own tinted band, so without this the cards here end
    // exactly on that band's top edge.
    <div id="features" style={{ paddingBottom: 104 }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "96px 32px 0", textAlign: "center" }}>
        <SectionBadge label="مميزات المنصة" />
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
                <div style={{ fontSize: 19, fontWeight: 700, color: TEAL }}>873400</div>
                <div style={{ background: GOOD_BG, color: GOOD_FG, fontSize: 9.5, fontWeight: 700, padding: "3px 7px", borderRadius: 8 }}>+4.5%</div>
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
                    <div style={{ fontSize: 20, fontWeight: 700, color: DARK }}>76</div>
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

function HowStepsSection() {
  return (
    <section
      id="steps"
      style={{
        padding: "96px 0 104px",
        backgroundColor: "#f4fbf9",
        backgroundImage:
          "linear-gradient(to right, rgba(4,43,41,0.035) 1px, transparent 1px),linear-gradient(to bottom, rgba(4,43,41,0.035) 1px, transparent 1px)",
        backgroundSize: "52px 52px",
        // Rounded top corners, as in the design — the band reads as its
        // own panel instead of a hard rule across the page.
        borderRadius: "44px 44px 0 0",
      }}
    >
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "0 32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 32, marginBottom: 60 }}>
          <h2 style={{ fontSize: 44, lineHeight: 1.25, letterSpacing: "-0.8px", fontWeight: 700, color: TEAL, margin: 0 }}>
            كيف تبدأ في 3 خطوات
          </h2>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 18, maxWidth: 360, textAlign: "right" }}>
            <p style={{ margin: 0, fontSize: 14.5, color: MUTED, lineHeight: 1.85 }}>
              أضف رابط موقعك ودع ظهور يحلله ويحسّن ظهورك بنقرة واحدة
            </p>
            <Link
              href="/preview"
              className="rl-fill"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                background: TEAL,
                color: "#fff",
                fontSize: 13.5,
                fontWeight: 700,
                padding: "13px 26px",
                borderRadius: 9999,
                whiteSpace: "nowrap",
                boxShadow: "0 12px 26px rgba(11,158,148,0.3)",
              }}
            >
              ابدأ مجاناً <span aria-hidden>←</span>
            </Link>
          </div>
        </div>

        <div className="rl-zh-grid-3" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 26 }}>
          <StepCard title="اربط موقعك" text="أضف رابط موقعك ودع ظهور يبدأ بفهم نشاطك وسوقك ومنافسيك">
            <Step1Mock />
          </StepCard>
          <StepCard title="اكتشف ما يمنع ظهورك" text="ظهور يحلل موقعك ووجودك في Google ومحركات الذكاء الاصطناعي ويحدد أهم فرص التحسين">
            <Step2Mock />
          </StepCard>
          <StepCard title="أصلحه بنقرة واحدة" text="راجع التحسينات المقترحة وطبّقها مباشرة ثم تابع تحسن ظهورك">
            <Step3Mock />
          </StepCard>
        </div>
      </div>
    </section>
  );
}

function StepCard({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 28,
        padding: 22,
        textAlign: "right",
        boxShadow: "0 2px 4px rgba(4,43,41,0.03),0 22px 48px rgba(4,43,41,0.07)",
      }}
    >
      {/* tinted inner panel — the white rows sit on top of it */}
      <div style={{ background: STEP_PANEL, borderRadius: 20, padding: 16, marginBottom: 26 }}>{children}</div>
      <div style={{ fontSize: 21, fontWeight: 700, color: DARK, marginBottom: 10 }}>{title}</div>
      <p style={{ margin: 0, fontSize: 14, color: MUTED, lineHeight: 1.85 }}>{text}</p>
    </div>
  );
}

function Step1Mock() {
  return (
    <div>
      <div style={{ fontSize: 12.5, fontWeight: 700, color: DARK, marginBottom: 14 }}>اربط موقعك</div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#fff", borderRadius: 14, padding: "6px 14px 6px 6px" }}>
          <span dir="ltr" style={{ flex: 1, minWidth: 0, fontSize: 11, color: "#b3c2c0", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            https://yourbrand.sa
          </span>
          <span style={{ background: TEAL, color: "#fff", fontSize: 10.5, fontWeight: 700, padding: "7px 15px", borderRadius: 9999, whiteSpace: "nowrap", flexShrink: 0 }}>
            اربط
          </span>
        </div>

        {STEP_1_ROWS.map((r) => (
          <div key={r.label} style={{ display: "flex", alignItems: "center", gap: 8, background: "#fff", borderRadius: 14, padding: "11px 12px" }}>
            <span
              style={{
                width: 20,
                height: 20,
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 3,
              }}
            >
              <DashIcon name={r.icon} color="#8fa9a5" />
            </span>
            <span style={{ flex: 1, fontSize: 11.5, fontWeight: 600, color: DARK }}>{r.label}</span>
            <span
              style={{
                background: r.pending ? "#fdf3e5" : "#e8f6f3",
                color: r.pending ? "#cf9235" : "#0b8f7d",
                fontSize: 9.5,
                fontWeight: 700,
                padding: "4px 10px",
                borderRadius: 9999,
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
            >
              {r.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Step2Mock() {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 14 }}>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: DARK }}>تحليل الظهور</span>
        <span style={{ background: TEAL, color: "#fff", fontSize: 9.5, fontWeight: 700, padding: "5px 11px", borderRadius: 9999, whiteSpace: "nowrap" }}>
          48 فرصة
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        {STEP_2_STATS.map((s) => (
          <div key={s.label} style={{ background: "#fff", borderRadius: 14, padding: "12px 12px 14px" }}>
            <div style={{ fontSize: 9, color: "#a9b8b7", marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 19, fontWeight: 700, color: DARK, marginBottom: 10, letterSpacing: "-0.3px" }}>{s.display}</div>
            <div style={{ height: 5, borderRadius: 5, background: "#eaf2f0" }}>
              <div style={{ height: "100%", width: `${s.pct}%`, borderRadius: 5, background: TEAL }} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {STEP_2_ISSUES.map((i) => (
          <div key={i.label} style={{ display: "flex", alignItems: "center", gap: 8, background: "#fff", borderRadius: 14, padding: "11px 12px" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: i.color, flexShrink: 0 }} />
            <span style={{ flex: 1, fontSize: 11, fontWeight: 600, color: DARK }}>{i.label}</span>
            <span
              style={{
                background: i.bg,
                color: i.color,
                fontSize: 9.5,
                fontWeight: 700,
                padding: "4px 11px",
                borderRadius: 9999,
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
            >
              {i.impact}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Step3Mock() {
  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 10 }}>
        {STEP_3_FIXES.map((f) => (
          <div key={f.label} style={{ display: "flex", alignItems: "center", gap: 8, background: "#fff", borderRadius: 14, padding: "11px 12px" }}>
            <span style={{ flex: 1, fontSize: 11, fontWeight: 600, color: DARK }}>{f.label}</span>
            <span
              style={{
                fontSize: 9.5,
                fontWeight: 700,
                padding: "5px 12px",
                borderRadius: 9999,
                whiteSpace: "nowrap",
                flexShrink: 0,
                background: f.done ? "#fff" : TEAL,
                color: f.done ? "#0b8f7d" : "#fff",
                border: f.done ? "1px solid #e0eeeb" : "none",
              }}
            >
              {f.status}
            </span>
          </div>
        ))}
      </div>

      <div style={{ background: "#fff", borderRadius: 14, padding: "12px 12px 10px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: DARK }}>مؤشر الظهور بعد التحسين</span>
          <span style={{ background: "#e8f6f3", color: "#0b8f7d", fontSize: 9.5, fontWeight: 700, padding: "4px 10px", borderRadius: 9999, whiteSpace: "nowrap" }}>
            +18%
          </span>
        </div>
        <StepTrendChart />
      </div>
    </div>
  );
}

// Area chart for "مؤشر الظهور بعد التحسين". SVG has no writing direction
// of its own, so index 0 is mapped to the right edge by hand to keep the
// curve reading right-to-left like the rest of the page.
function StepTrendChart() {
  const n = STEP_3_TREND.length;
  const pts = STEP_3_TREND.map((v, i) => ({
    x: 100 - (i / (n - 1)) * 100,
    y: 40 - (v / 100) * 34,
  }));
  let line = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < n; i++) {
    const midX = (pts[i - 1].x + pts[i].x) / 2;
    line += ` C ${midX} ${pts[i - 1].y} ${midX} ${pts[i].y} ${pts[i].x} ${pts[i].y}`;
  }
  const area = `${line} L ${pts[n - 1].x} 40 L ${pts[0].x} 40 Z`;

  return (
    <div style={{ display: "flex", gap: 6 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <svg viewBox="0 0 100 40" preserveAspectRatio="none" style={{ display: "block", width: "100%", height: 54 }}>
          <defs>
            <linearGradient id="zhStepTrend" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={TEAL} stopOpacity="0.26" />
              <stop offset="100%" stopColor={TEAL} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill="url(#zhStepTrend)" />
          <path d={line} fill="none" stroke={TEAL} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        </svg>
        <div style={{ display: "flex", marginTop: 6 }}>
          {STEP_3_MONTHS.map((m) => (
            <span key={m} style={{ flex: 1, textAlign: "center", fontSize: 8, color: "#bcc9c8" }}>
              {m}
            </span>
          ))}
        </div>
      </div>
      <div style={{ height: 54, display: "flex", flexDirection: "column", justifyContent: "space-between", fontSize: 7, color: "#cfdcda", flexShrink: 0 }}>
        <span>100</span>
        <span>50</span>
        <span>0</span>
      </div>
    </div>
  );
}

// The first testimonial gets the filled teal treatment; the rest are
// plain cards. Rendered from one keyed map rather than a static element
// plus a map, so every child carries a key.
function TestimonialsSection() {
  return (
    <div id="testimonials" style={{ maxWidth: 1120, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="آراء العملاء" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 52px", maxWidth: 560 }}>
        قالوا عن ظهور
      </h2>
      <div className="rl-zh-grid-3" style={{ display: "grid", gridTemplateColumns: "1.25fr 1fr 1fr", gap: 24, textAlign: "right" }}>
        {TESTIMONIALS.map((t, i) =>
          i === 0 ? (
            <div
              key={t.company}
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
                <div style={{ fontSize: 17.5, lineHeight: 1.8 }}>{t.quote}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 32 }}>
                <div style={{ width: 38, height: 38, borderRadius: "50%", background: "rgba(255,255,255,0.25)" }} />
                <b style={{ fontSize: 13.5 }}>{t.company}</b>
              </div>
            </div>
          ) : (
            <div
              key={t.company}
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
                <b style={{ fontSize: 13, color: DARK }}>{t.company}</b>
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}

function PricingSection({ onOpenModal }: { onOpenModal: () => void }) {
  return (
    <div id="pricing" style={{ maxWidth: 1120, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="الأسعار" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 16px", maxWidth: 520 }}>
        اختر الخطة المناسبة لظهورك
      </h2>
      <p style={{ fontSize: 15.5, color: MUTED, maxWidth: 460, margin: "0 auto 30px", lineHeight: 1.8 }}>
        ابدأ بتحسين ظهور موقعك واختر الخطة المناسبة لاحتياجك
      </p>
      <div style={{ display: "inline-flex", background: "#f5f8f8", borderRadius: 26, padding: 5, gap: 4, marginBottom: 44 }}>
        <div style={{ background: TEAL, color: "#fff", fontSize: 13, fontWeight: 700, padding: "9px 24px", borderRadius: 22, whiteSpace: "nowrap" }}>شهري</div>
        <div style={{ color: MUTED, fontSize: 13, fontWeight: 700, padding: "9px 24px", whiteSpace: "nowrap" }}>سنوي · خصم 50%</div>
      </div>
      <div className="rl-zh-grid-3" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, textAlign: "right" }}>
        {PLANS.map((plan) => {
          const isContact = !plan.period;
          return (
            <div
              key={plan.name}
              style={{
                position: "relative",
                borderRadius: 24,
                padding: "32px 28px",
                display: "flex",
                flexDirection: "column",
                background: plan.bg,
                border: plan.border,
                boxShadow: plan.boxShadow,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 13.5, fontWeight: 700, color: plan.nameColor }}>{plan.name}</span>
                {plan.badge && (
                  <span
                    style={{
                      background: "rgba(255,255,255,0.22)",
                      color: "#fff",
                      fontSize: 10.5,
                      fontWeight: 700,
                      padding: "4px 11px",
                      borderRadius: 9999,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {plan.badge}
                  </span>
                )}
              </div>

              {plan.oldPrice && (
                <div style={{ fontSize: 14, color: plan.mutedColor, textDecoration: "line-through", marginBottom: 4 }}>{plan.oldPrice}</div>
              )}
              <div style={{ fontSize: isContact ? 27 : 38, fontWeight: 700, letterSpacing: "-0.8px", color: plan.priceColor }}>
                {plan.price}
                {plan.period && (
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: plan.mutedColor, letterSpacing: 0 }}>{plan.period}</span>
                )}
              </div>

              <div style={{ fontSize: 14, color: plan.mutedColor, margin: "12px 0 26px", lineHeight: 1.75 }}>{plan.desc}</div>

              {isContact ? (
                <button
                  onClick={onOpenModal}
                  className="rl-fill-soft"
                  style={{
                    textAlign: "center",
                    fontSize: 13.5,
                    fontWeight: 700,
                    padding: 12,
                    borderRadius: 24,
                    marginBottom: 26,
                    cursor: "pointer",
                    background: plan.btnBg,
                    color: plan.btnColor,
                    border: plan.btnBorder,
                  }}
                >
                  {plan.cta}
                </button>
              ) : (
                <Link
                  href="/preview"
                  className="rl-fill-soft"
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
                </Link>
              )}

              {plan.features.map((pf) => (
                <div key={pf} style={{ display: "flex", gap: 9, fontSize: 13.5, color: plan.featColor, padding: "6px 0" }}>
                  <span style={{ color: plan.checkColor, flexShrink: 0 }}>✓</span>
                  {pf}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);
  return (
    <div id="faq" style={{ maxWidth: 820, margin: "0 auto", padding: "104px 32px 0", textAlign: "center" }}>
      <SectionBadge label="الأسئلة الشائعة" />
      <h2 style={{ fontSize: 42, lineHeight: 1.25, letterSpacing: "-0.6px", fontWeight: 700, color: DARK, margin: "0 auto 44px" }}>
        لديك سؤال؟ لدينا الإجابة
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, textAlign: "right" }}>
        {FAQS.map(([q, a], i) => {
          const open = openIndex === i;
          return (
            <div
              key={q}
              style={{
                border: `1px solid ${BORDER}`,
                borderRadius: 18,
                background: "#fff",
                boxShadow: "0 2px 4px rgba(4,43,41,0.02),0 12px 30px rgba(4,43,41,0.04)",
                overflow: "hidden",
              }}
            >
              <button
                onClick={() => setOpenIndex(open ? null : i)}
                aria-expanded={open}
                className="rl-faq-row"
                style={{
                  width: "100%",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 16,
                  textAlign: "right",
                  background: "transparent",
                  border: 0,
                  cursor: "pointer",
                  padding: "20px 24px",
                  fontSize: 15,
                  fontWeight: 600,
                  color: DARK,
                }}
              >
                <span style={{ flex: 1 }}>{q}</span>
                <span
                  aria-hidden
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    background: "#eefaf8",
                    color: TEAL,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 16,
                    flexShrink: 0,
                  }}
                >
                  {open ? "−" : "+"}
                </span>
              </button>
              {open && (
                <p style={{ margin: 0, padding: "0 24px 20px", fontSize: 14, lineHeight: 1.95, color: MUTED }}>{a}</p>
              )}
            </div>
          );
        })}
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
        <div style={{ paddingTop: 22 }}>© 2026 ظهور. جميع الحقوق محفوظة.</div>
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
