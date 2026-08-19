"use client";

import Link from "next/link";
import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

import { BrandMark } from "@/components/ui/BrandMark";

import "./landing.css";

const WORDS = ["إيرادات", "أرباح", "عملاء"];

const DEMOS = [
  { q: "أفضل محل سباكة في الرياض" },
  { q: "أفضل متجر لأدوات القهوة" },
  { q: "أفضل شركة تنظيف منازل" },
  { q: "أفضل متجر أثاث مكتبي" },
  { q: "أفضل عيادة أسنان للأطفال" },
  { q: "ورشة صيانة مكيفات" },
];

type Pin = {
  q: string;
  pos: CSSProperties;
  floatAnim: string;
  haloAnim: string;
  size: number;
  labelSize: number;
  labelPad: string;
  hideSm?: boolean;
};

const PINS: Pin[] = [
  {
    q: DEMOS[0].q,
    pos: { top: "44%", right: "2%" },
    floatAnim: "rrise .7s .1s ease both, rfa 7.5s 1s ease-in-out infinite",
    haloAnim: "rhalo 3.4s ease-in-out infinite",
    size: 26,
    labelSize: 11.5,
    labelPad: "7px 14px",
  },
  {
    q: DEMOS[1].q,
    pos: { top: "42%", left: "2%" },
    floatAnim: "rrise .7s .2s ease both, rfb 8.5s .3s ease-in-out infinite",
    haloAnim: "rhalo 3.8s .4s ease-in-out infinite",
    size: 26,
    labelSize: 11.5,
    labelPad: "7px 14px",
  },
  {
    q: DEMOS[2].q,
    pos: { bottom: "18%", left: "8%" },
    floatAnim: "rrise .7s .3s ease both, rfc 10s .5s ease-in-out infinite",
    haloAnim: "rhalo 3.2s .8s ease-in-out infinite",
    size: 26,
    labelSize: 11.5,
    labelPad: "7px 14px",
  },
  {
    q: DEMOS[3].q,
    pos: { bottom: "6%", left: "28%" },
    floatAnim: "rrise .7s .4s ease both, rfa 9s .8s ease-in-out infinite",
    haloAnim: "rhalo 4.2s .2s ease-in-out infinite",
    size: 23,
    labelSize: 11,
    labelPad: "6px 13px",
    hideSm: true,
  },
  {
    q: DEMOS[4].q,
    pos: { top: "16%", right: "7%" },
    floatAnim: "rrise .7s .5s ease both, rfb 11s .2s ease-in-out infinite",
    haloAnim: "rhalo 3.6s .6s ease-in-out infinite",
    size: 23,
    labelSize: 11,
    labelPad: "6px 13px",
  },
  {
    q: DEMOS[5].q,
    pos: { top: "11%", left: "8%" },
    floatAnim: "rrise .7s .6s ease both, rfc 12s .9s ease-in-out infinite",
    haloAnim: "rhalo 4s 1s ease-in-out infinite",
    size: 23,
    labelSize: 11,
    labelPad: "6px 13px",
    hideSm: true,
  },
];

const FAQS: [string, string][] = [
  [
    "ما الذي يرصده ظهور فعلياً؟",
    "أسئلة المشترين عبر خمس منصات ذكاء اصطناعي: أي الإجابات تذكر علامتك، وترتيبك داخلها، والمنافسون الذين يظهرون بدلاً منك، وانطباع كل ذكر، وكل نطاق استُشهد به كدليل.",
  ],
  [
    "كيف يختار ظهور الأسئلة التي يتتبعها؟",
    "نولّد أسئلة الفئة والمقارنة والبدائل والأسئلة المرتبطة باسم علامتك انطلاقاً من نطاقك وسوقك، ثم يمكنك تعديل أي سؤال أو إضافته أو حذفه.",
  ],
  [
    "ما المنصات المشمولة؟",
    "ChatGPT وGemini وPerplexity ووضع الذكاء الاصطناعي في جوجل ونظرات جوجل العامة — تُحلّل على الجدول نفسه لتبقى النتائج قابلة للمقارنة.",
  ],
  [
    "هل يمكنني تتبّع المنافسين؟",
    "نعم. أضف المنافسين يدوياً أو دع ظهور يكتشف العلامات المتكررة في إجاباتك، ثم قارن حصة الصوت والظهور جنباً إلى جنب.",
  ],
  [
    "هل يُنشر المحتوى تلقائياً؟",
    "لا. كل مقال يمرّ بمسودة ثم مراجعة ثم اعتماد، والنشر التلقائي اختياري لكل تكامل على حدة.",
  ],
  [
    "أين يمكن لظهور أن ينشر؟",
    "ووردبريس، ويبفلو، غوست، شوبيفاي، ونوشن — أو تصدير المحتوى إلى أي مسار عمل يستخدمه فريقك.",
  ],
];

export default function Home() {
  const [dark, setDark] = useState(false);
  const [rotIndex, setRotIndex] = useState(0);
  const [rotOn, setRotOn] = useState(true);
  const [ping, setPing] = useState(0);
  const [activeDemo, setActiveDemo] = useState<number | null>(null);
  const [domain, setDomain] = useState("");
  const [openFaqs, setOpenFaqs] = useState<Record<number, boolean>>({ 0: true });

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem("rasid-mode");
    } catch {
      // localStorage unavailable (private mode, etc.) — fall back to light.
    }
    // Deliberately deferred to an effect (not a lazy useState initializer):
    // localStorage is unavailable during SSR, so reading it during render
    // would desync the server-rendered HTML from the client's first paint.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved === "dark") setDark(true);
  }, []);

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

  useEffect(() => {
    const timer = setInterval(() => setPing((p) => (p + 1) % 6), 2200);
    return () => clearInterval(timer);
  }, []);

  const toggleDark = () => {
    const next = !dark;
    setDark(next);
    try {
      localStorage.setItem("rasid-mode", next ? "dark" : "light");
    } catch {
      // ignore
    }
  };

  const toggleFaq = (index: number) => setOpenFaqs((s) => ({ ...s, [index]: !s[index] }));

  const activeQuery = (activeDemo != null ? DEMOS[activeDemo] : DEMOS[ping]).q;

  return (
    <div
      dir="rtl"
      data-mode={dark ? "dark" : undefined}
      className="rasid-landing"
      style={{ position: "relative", minHeight: "100vh", overflowX: "clip" }}
    >
      <div style={{ position: "relative", zIndex: 1 }}>
        <Header dark={dark} onToggleDark={toggleDark} />
        <Hero
          ping={ping}
          onPick={setActiveDemo}
          activeQuery={activeQuery}
          rotWord={WORDS[rotIndex]}
          rotOn={rotOn}
          domain={domain}
          onDomainChange={setDomain}
        />
        <Features />
        <Solution />
        <Faq faqs={FAQS} open={openFaqs} onToggle={toggleFaq} />
        <Footer />
      </div>
    </div>
  );
}

function Header({ dark, onToggleDark }: { dark: boolean; onToggleDark: () => void }) {
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        background: "var(--fade-top)",
        backdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--line)",
      }}
    >
      <nav
        style={{
          width: "min(1180px,100%)",
          margin: "0 auto",
          padding: "0 28px",
          height: 62,
          display: "flex",
          alignItems: "center",
          gap: 26,
        }}
      >
        <a href="#top" style={{ display: "flex", alignItems: "center", gap: 9, fontWeight: 600, fontSize: 16.5 }}>
          <BrandMark className="h-[22px] w-[22px]" />
          ظهور
        </a>
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 26,
            fontSize: 13.5,
            color: "var(--mut)",
          }}
        >
          <a href="#features" style={{ color: "inherit" }}>الخصائص</a>
          <a href="#solution" style={{ color: "inherit" }}>الحل</a>
          <a href="#faq" style={{ color: "inherit" }}>الأسئلة الشائعة</a>
        </div>
        <button
          onClick={onToggleDark}
          aria-label="تغيير المود"
          className="rl-icon-btn"
          style={{
            width: 34,
            height: 34,
            flex: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: "1px solid var(--line)",
            borderRadius: 9999,
            background: "var(--panel)",
            cursor: "pointer",
            fontSize: 14,
            color: "var(--tx)",
          }}
        >
          {dark ? "☀" : "☾"}
        </button>
        <Link
          href="/preview"
          className="rl-fill"
          style={{
            display: "inline-flex",
            alignItems: "center",
            fontSize: 13,
            fontWeight: 500,
            color: "var(--btn-fg)",
            background: "var(--tx)",
            padding: "9px 16px",
            borderRadius: 9999,
            whiteSpace: "nowrap",
          }}
        >
          تسجيل الدخول
        </Link>
      </nav>
    </header>
  );
}

function Pinned({ pin, index, ping, onPick }: { pin: Pin; index: number; ping: number; onPick: (i: number) => void }) {
  const active = index === ping;
  const inset = pin.size === 26 ? { ring: 0, white: 5, dot: 8 } : { ring: 0, white: 4, dot: 7 };
  return (
    <button
      onClick={() => onPick(index)}
      data-pin-sm={pin.hideSm ? "hide" : undefined}
      style={{
        position: "absolute",
        ...pin.pos,
        border: 0,
        background: "transparent",
        padding: 0,
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: pin.size === 26 ? 8 : 7,
        animation: pin.floatAnim,
      }}
    >
      <span
        style={{
          whiteSpace: "nowrap",
          fontSize: pin.labelSize,
          color: "#fff",
          background: "#16181d",
          borderRadius: 9999,
          padding: pin.labelPad,
          boxShadow: "0 8px 20px rgba(17,24,39,.28)",
        }}
      >
        {pin.q}
      </span>
      <span style={{ position: "relative", width: pin.size, height: pin.size, display: "block" }}>
        <span
          style={{
            position: "absolute",
            inset: inset.ring,
            borderRadius: "50%",
            background: "rgba(22,24,29,.16)",
            animation: pin.haloAnim,
          }}
        />
        <span style={{ position: "absolute", inset: inset.white, borderRadius: "50%", background: "#fff" }} />
        <span
          style={{
            position: "absolute",
            inset: inset.dot,
            borderRadius: "50%",
            background: active ? "var(--acc)" : "#16181d",
            transition: "background .3s ease",
          }}
        />
      </span>
    </button>
  );
}

function Hero({
  ping,
  onPick,
  activeQuery,
  rotWord,
  rotOn,
  domain,
  onDomainChange,
}: {
  ping: number;
  onPick: (i: number) => void;
  activeQuery: string;
  rotWord: string;
  rotOn: boolean;
  domain: string;
  onDomainChange: (v: string) => void;
}) {
  return (
    <section
      id="top"
      style={{
        position: "relative",
        height: "calc(100svh - 62px)",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 28px 32px",
      }}
    >
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          overflow: "hidden",
          backgroundImage: "url('/landing/city-map.jpg')",
          backgroundSize: "cover",
          backgroundPosition: "center 45%",
          opacity: "var(--map-opacity)",
          filter: "var(--map-filter)",
          maskImage: "radial-gradient(120% 100% at 50% 45%,#000 45%,transparent 92%)",
          WebkitMaskImage: "radial-gradient(120% 100% at 50% 45%,#000 45%,transparent 92%)",
        }}
      />
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background:
            "radial-gradient(680px 380px at 50% 50%,var(--fade-core) 40%,var(--fade-mid) 70%,var(--fade-soft) 100%),linear-gradient(to bottom,var(--fade-top),transparent 30%,transparent 72%,var(--bg))",
        }}
      />

      {PINS.map((pin, i) => (
        <Pinned key={pin.q} pin={pin} index={i} ping={ping} onPick={onPick} />
      ))}

      <div
        data-pin-sm="hide"
        style={{
          position: "absolute",
          bottom: "2%",
          right: "1.5%",
          width: 215,
          border: "1px solid var(--line)",
          borderRadius: 20,
          background: "var(--panel)",
          boxShadow: "0 20px 50px rgba(17,24,39,.16)",
          padding: 16,
          textAlign: "right",
          animation: "rrise .7s .3s ease both",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--acc)",
              animation: "rpulse 2s ease-in-out infinite",
            }}
          />
          <span style={{ fontSize: 11, color: "var(--dim)" }}>تنبيه مباشر</span>
        </div>
        <div style={{ marginTop: 10, fontSize: 13.5, fontWeight: 600, lineHeight: 1.6 }}>
          ظهر موقعك في عملية بحث جديدة
        </div>
        <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--mut)", lineHeight: 1.7 }}>«{activeQuery}»</div>
        <div style={{ marginTop: 12, display: "flex", alignItems: "baseline", gap: 7 }}>
          <span style={{ fontSize: 12, color: "var(--dim)" }}>المركز</span>
          <span className="mono" style={{ fontSize: 20, fontWeight: 600, color: "var(--acc)" }}>٣</span>
          <span style={{ fontSize: 11, color: "var(--dim)" }}>ذُكرت في ٤ من ٥ منصات</span>
        </div>
        <div style={{ marginTop: 10, display: "flex", gap: 5 }}>
          {[0, 1, 2, 3].map((i) => (
            <span key={i} style={{ flex: 1, height: 6, borderRadius: 3, background: "var(--acc)" }} />
          ))}
          <span style={{ flex: 1, height: 6, borderRadius: 3, background: "#e6e3ea" }} />
        </div>
      </div>

      <div
        style={{
          position: "relative",
          zIndex: 3,
          width: "min(720px,100%)",
          margin: "0 auto",
          textAlign: "center",
          animation: "rrise .6s ease both",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 9,
            padding: "5px 6px 5px 15px",
            border: "1px solid var(--line)",
            borderRadius: 9999,
            background: "var(--panel)",
            fontSize: 12.5,
            color: "var(--mut)",
            whiteSpace: "nowrap",
            boxShadow: "0 2px 10px rgba(17,24,39,.05)",
          }}
        >
          <span
            className="mono"
            style={{
              fontSize: 10,
              letterSpacing: ".08em",
              padding: "3px 9px",
              borderRadius: 9999,
              background: "rgba(14,157,134,.16)",
              color: "var(--acc)",
            }}
          >
            جديد
          </span>
          تتبّع الاستشهادات داخل خمس منصات ذكاء اصطناعي
        </div>

        <h1
          style={{
            margin: "14px auto 0",
            fontSize: "clamp(28px,3.8vw,46px)",
            lineHeight: 1.26,
            letterSpacing: "-.02em",
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          حوّل المحادثات إلى{" "}
          <span
            style={{
              display: "inline-block",
              color: "var(--acc)",
              transition: "opacity .35s ease",
              opacity: rotOn ? 1 : 0,
            }}
          >
            {rotWord}
          </span>
        </h1>
        <p
          style={{
            margin: "14px auto 0",
            maxWidth: 560,
            fontSize: 15.5,
            lineHeight: 1.85,
            color: "var(--mut)",
          }}
        >
          اجعل علامتك التجارية أسهل على محرّكات الذكاء الاصطناعي كي تجدها وتستشهد بها وتوصي بها في الإجابات التي يثق بها عملاؤك قبل الشراء.
        </p>

        <form
          onSubmit={(e) => e.preventDefault()}
          style={{
            margin: "22px auto 0",
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
            <span className="mono" style={{ fontSize: 12.5, color: "var(--dim)" }}>https://</span>
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
            ابدأ مجاناً
          </Link>
        </form>
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--dim)" }}>بدون بطاقة ائتمانية · أول تقرير خلال ٣ دقائق</div>

        <div style={{ margin: "18px auto 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <div style={{ fontSize: 13, color: "var(--mut)" }}>موثوق من أكثر من ٥٠٠ نشاط محلي</div>
          {/* eslint-disable @next/next/no-img-element */}
          <div style={{ display: "flex", alignItems: "center" }} dir="ltr">
            {[12, 32, 15, 45].map((id, i) => (
              <img
                key={id}
                src={`https://i.pravatar.cc/80?img=${id}`}
                alt=""
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: "50%",
                  objectFit: "cover",
                  border: "2px solid var(--panel)",
                  marginLeft: -8,
                  background: i % 2 ? "#ded9e8" : "#e7e3ee",
                }}
              />
            ))}
            <span
              style={{
                height: 34,
                display: "flex",
                alignItems: "center",
                padding: "0 12px",
                marginLeft: -8,
                borderRadius: 9999,
                background: "rgba(14,157,134,.16)",
                border: "2px solid var(--panel)",
                fontFamily: "var(--font-jetbrains-mono),monospace",
                fontSize: 12,
                color: "var(--acc)",
              }}
            >
              +500
            </span>
          </div>
          {/* eslint-enable @next/next/no-img-element */}
        </div>
      </div>
    </section>
  );
}

function EyebrowTag({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        fontSize: 12,
        color: "var(--mut)",
        border: "1px solid var(--line)",
        borderRadius: 9999,
        padding: "6px 14px",
        background: "var(--panel)",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--acc)" }} />
      {children}
    </span>
  );
}

function CircularGauge({ percent, size = 168, stroke = 14 }: { percent: number; size?: number; stroke?: number }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - percent / 100);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)", display: "block" }}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--panel2)" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--acc)"
        strokeWidth={stroke}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
      />
    </svg>
  );
}

function Features() {
  const rowGrid: CSSProperties = {
    padding: "26px 0",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))",
    gap: 44,
    alignItems: "center",
  };
  const panel: CSSProperties = {
    border: "1px solid var(--line)",
    borderRadius: 26,
    background: "var(--panel)",
    boxShadow: "0 24px 60px rgba(17,24,39,.10)",
    padding: 26,
  };
  const h3: CSSProperties = {
    margin: "18px 0 0",
    fontSize: "clamp(24px,2.6vw,32px)",
    fontWeight: 600,
    letterSpacing: "-.02em",
    lineHeight: 1.35,
  };
  const body: CSSProperties = { margin: "14px 0 0", fontSize: 15, lineHeight: 1.95, color: "var(--mut)", maxWidth: 420 };

  const visibilityRows = [
    ["أفضل محل سباكة في الرياض", 92, "٩٢٪"],
    ["أفضل متجر لأدوات القهوة", 76, "٧٦٪"],
    ["أفضل متجر أثاث مكتبي", 54, "٥٤٪"],
    ["أفضل عيادة أسنان للأطفال", 38, "٣٨٪"],
    ["ورشة صيانة مكيفات", 24, "٢٤٪"],
  ] as const;

  const brandBars = [
    ["أنت", 215, "var(--acc)"],
    ["منافس أ", 158, "#d8c2f7"],
    ["منافس ب", 118, "#e5e7eb"],
    ["منافس ج", 78, "#eceef1"],
  ] as const;

  const citations = [
    ["دليل الخدمات المحلي", "١٥", false],
    ["موقعك الرسمي", "١٣", true],
    ["مراجعات المستخدمين", "١٠", false],
    ["منتديات محلية", "٠٨", false],
    ["مقالات مقارنة", "٠٥", false],
  ] as const;

  return (
    <section id="features" style={{ padding: "48px 28px 52px" }}>
      <div style={{ width: "min(1180px,100%)", margin: "0 auto", textAlign: "center" }}>
        <div className="mono" style={{ fontSize: 11, letterSpacing: ".16em", color: "var(--acc)" }}>01 — الخصائص</div>
        <h2
          style={{
            margin: "14px auto 0",
            maxWidth: 700,
            fontSize: "clamp(24px,2.8vw,34px)",
            lineHeight: 1.4,
            letterSpacing: "-.02em",
            fontWeight: 600,
          }}
        >
          كل ما تحتاجه لقياس حضورك في إجابات الذكاء الاصطناعي
        </h2>
        <p style={{ margin: "14px auto 0", maxWidth: 520, fontSize: 14.5, lineHeight: 1.85, color: "var(--mut)" }}>
          من رصد الأسئلة التي يطرحها المشترون، إلى تتبّع المصادر التي تستشهد بها النماذج.
        </p>

        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", textAlign: "right" }}>
          <div style={rowGrid}>
            <div style={{ padding: 8 }}>
              <EyebrowTag>رصد الأسئلة</EyebrowTag>
              <h3 style={h3}>اكتشف أين تُذكر علامتك</h3>
              <p style={body}>تتبّع أسئلة التوصية والمقارنة والبدائل التي يطرحها المشترون قبل اتخاذ القرار.</p>
            </div>
            <div style={panel}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  border: "1px solid var(--line)",
                  borderRadius: 9999,
                  background: "var(--panel2)",
                  padding: "13px 18px",
                  fontSize: 15,
                  color: "var(--mut)",
                }}
              >
                أفضل شركة تنظيف منازل
                <span style={{ flex: 1 }} />
                <span className="mono" style={{ fontSize: 12, color: "var(--dim)" }}>بحث</span>
              </div>
              <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 14 }}>
                {visibilityRows.map(([label, pct, display]) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 15 }}>
                    <span style={{ flex: 1 }}>{label}</span>
                    <span style={{ width: 110, height: 8, borderRadius: 4, background: "var(--panel2)", overflow: "hidden" }}>
                      <span style={{ display: "block", height: "100%", width: `${pct}%`, background: "var(--acc)" }} />
                    </span>
                    <span className="mono" style={{ fontSize: 13, color: "var(--mut)" }}>{display}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ ...rowGrid, alignItems: "start" }}>
            <div style={{ position: "relative", paddingBottom: 34 }}>
              <div style={{ ...panel, display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 26px" }}>
                <div style={{ alignSelf: "flex-start", fontSize: 14.5, color: "var(--mut)" }}>نسبة ظهورك الإجمالية</div>
                <div style={{ position: "relative", marginTop: 22, display: "inline-flex" }}>
                  <CircularGauge percent={68} />
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <span className="mono" style={{ fontSize: 32, fontWeight: 700, color: "var(--tx)" }}>٦٨٪</span>
                    <span style={{ marginTop: 4, fontSize: 11.5, color: "var(--dim)" }}>من عمليات البحث</span>
                  </div>
                </div>
              </div>
              <div
                style={{
                  ...panel,
                  position: "absolute",
                  bottom: 0,
                  left: -18,
                  width: "62%",
                  minWidth: 190,
                  padding: 18,
                  borderRadius: 20,
                  boxShadow: "0 18px 40px rgba(17,24,39,.14)",
                }}
              >
                <div style={{ fontSize: 12.5, color: "var(--mut)" }}>الظهور حسب العلامة</div>
                <div style={{ marginTop: 14, display: "flex", alignItems: "flex-end", gap: 10, height: 92 }}>
                  {brandBars.map(([label, height, color]) => (
                    <div key={label} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                      <span style={{ width: "100%", height: height / 2.4, borderRadius: "8px 8px 3px 3px", background: color }} />
                      <span style={{ fontSize: 10, color: "var(--dim)", whiteSpace: "nowrap" }}>{label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div style={{ padding: 8 }}>
              <EyebrowTag>قياس الظهور</EyebrowTag>
              <h3 style={h3}>اعرف من يظهر بدلاً منك</h3>
              <p style={body}>اعرف متى تظهر علامتك، وفي أي ترتيب، ومن المنافس الذي يُوصى به بدلاً منك.</p>
            </div>
          </div>

          <div style={{ ...rowGrid, alignItems: "start" }}>
            <div style={{ padding: 8 }}>
              <EyebrowTag>تتبّع الاستشهادات</EyebrowTag>
              <h3 style={h3}>حوّل المحادثات إلى إيرادات</h3>
              <p style={body}>اعرف الصفحات والمنتديات والناشرين التي تستخدمها الإجابات كدليل، وأين تغيب صفحاتك.</p>
            </div>
            <div style={{ position: "relative", paddingTop: 20 }}>
              <div style={panel}>
                <div style={{ fontSize: 14.5, color: "var(--mut)" }}>أكثر المصادر استشهاداً</div>
                <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                  {citations.map(([label, count, accent]) => (
                    <div key={label} style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 15 }}>
                      <span
                        style={{
                          width: 40,
                          height: 40,
                          borderRadius: 12,
                          background: accent ? "rgba(14,157,134,.14)" : "var(--panel2)",
                        }}
                      />
                      <span style={{ flex: 1 }}>{label}</span>
                      <span className="mono" style={{ fontSize: 14, color: accent ? "var(--acc)" : "var(--mut)" }}>{count}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div
                style={{
                  ...panel,
                  position: "absolute",
                  top: 0,
                  right: 22,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 16px",
                  borderRadius: 9999,
                  boxShadow: "0 14px 32px rgba(17,24,39,.14)",
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--acc)" }} />
                <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: "var(--tx)" }}>٪38</span>
                <span style={{ fontSize: 11.5, color: "var(--mut)", whiteSpace: "nowrap" }}>تستشهد بموقعك</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Solution() {
  const cell: CSSProperties = {
    justifySelf: "center",
    padding: "20px 22px",
    border: "1px solid var(--line)",
    borderRadius: 18,
    background: "var(--panel)",
    boxShadow: "0 4px 14px rgba(17,24,39,.04)",
    display: "inline-flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 10,
  };
  const items = [
    "رصد الأسئلة",
    "قياس الظهور",
    "تحليل الإجابات",
    "تتبّع الاستشهادات",
    null, // center — ظهور itself
    "مراقبة المنافسين",
    "توليد المحتوى",
    "النشر إلى موقعك",
    "تقارير أسبوعية",
  ];

  return (
    <section id="solution" style={{ padding: "0 28px 52px" }}>
      <div style={{ width: "min(1180px,100%)", margin: "0 auto", textAlign: "center" }}>
        <div className="mono" style={{ fontSize: 11, letterSpacing: ".16em", color: "var(--acc)" }}>02 — الحل</div>
        <h2
          style={{
            margin: "14px auto 0",
            maxWidth: 720,
            fontSize: "clamp(24px,2.8vw,34px)",
            lineHeight: 1.4,
            letterSpacing: "-.02em",
            fontWeight: 600,
          }}
        >
          كل احتياجك في مكان واحد
        </h2>
        <p style={{ margin: "14px auto 0", maxWidth: 540, fontSize: 14.5, lineHeight: 1.85, color: "var(--mut)" }}>
          من رصد الأسئلة إلى نشر المحتوى الذي يرفع ظهورك — دون أدوات متفرقة.
        </p>

        <div
          style={{
            marginTop: 32,
            display: "grid",
            gridTemplateColumns: "repeat(3,auto)",
            justifyContent: "center",
            alignItems: "center",
            gap: "20px 28px",
            textAlign: "center",
          }}
        >
          {items.map((label) =>
            label ? (
              <div key={label} style={cell}>
                <span style={{ width: 32, height: 32, borderRadius: 11, background: "var(--panel2)", display: "block" }} />
                <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>{label}</span>
              </div>
            ) : (
              <div
                key="center"
                style={{
                  justifySelf: "center",
                  padding: "26px 30px",
                  border: "1px solid var(--line)",
                  borderRadius: 22,
                  background: "var(--panel)",
                  boxShadow: "0 10px 30px rgba(14,157,134,.14)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 11,
                }}
              >
                <span style={{ width: 30, height: 30, borderRadius: 9, background: "var(--acc)", display: "block" }} />
                <span style={{ fontSize: 19, fontWeight: 600, whiteSpace: "nowrap" }}>ظهور</span>
              </div>
            ),
          )}
        </div>
      </div>
    </section>
  );
}

function Faq({
  faqs,
  open,
  onToggle,
}: {
  faqs: [string, string][];
  open: Record<number, boolean>;
  onToggle: (i: number) => void;
}) {
  return (
    <section id="faq" style={{ padding: "0 28px 60px" }}>
      <div style={{ width: "min(1180px,100%)", margin: "0 auto", textAlign: "center" }}>
        <div className="mono" style={{ fontSize: 11, letterSpacing: ".16em", color: "var(--acc)" }}>03 — الأسئلة الشائعة</div>
        <h2 style={{ margin: "14px 0 0", fontSize: "clamp(24px,2.8vw,34px)", letterSpacing: "-.02em", fontWeight: 600 }}>
          أسئلة يطرحها الفريق قبل البدء
        </h2>
        <div
          style={{
            margin: "34px auto 0",
            maxWidth: 780,
            border: "1px solid var(--line)",
            borderRadius: 24,
            background: "var(--panel)",
            overflow: "hidden",
            textAlign: "right",
          }}
        >
          {faqs.map(([q, a], i) => (
            <div key={q} style={{ borderTop: i === 0 ? "none" : "1px solid var(--line)" }}>
              <button
                onClick={() => onToggle(i)}
                className="rl-faq-row"
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  textAlign: "right",
                  background: "transparent",
                  border: 0,
                  cursor: "pointer",
                  color: "var(--tx)",
                  fontSize: 14.5,
                  fontWeight: 500,
                  padding: "18px 22px",
                }}
              >
                <span style={{ flex: 1 }}>{q}</span>
                <span style={{ fontSize: 20, fontWeight: 300, color: "var(--mut)" }}>{open[i] ? "−" : "+"}</span>
              </button>
              {open[i] && (
                <p style={{ margin: 0, padding: "0 22px 18px 54px", fontSize: 13.5, lineHeight: 1.95, color: "var(--mut)" }}>
                  {a}
                </p>
              )}
            </div>
          ))}
        </div>
        <div
          style={{
            margin: "48px auto 0",
            maxWidth: 780,
            border: "1px solid var(--line)",
            borderRadius: 24,
            background: "radial-gradient(600px 220px at 50% 100%,rgba(14,157,134,.14),transparent 70%),var(--panel)",
            padding: "48px 28px",
          }}
        >
          <h3 style={{ margin: 0, fontSize: "clamp(21px,2.4vw,28px)", fontWeight: 600, letterSpacing: "-.02em" }}>
            قِس ظهورك اليوم
          </h3>
          <p style={{ margin: "12px auto 0", maxWidth: 440, fontSize: 14, lineHeight: 1.85, color: "var(--mut)" }}>
            ابدأ من الأسئلة التي يطرحها عملاؤك فعلاً، وتابع كيف يتغيّر حضورك أسبوعاً بعد أسبوع.
          </p>
          <Link
            href="/preview"
            className="rl-fill"
            style={{
              display: "inline-block",
              marginTop: 22,
              fontSize: 13.5,
              fontWeight: 600,
              color: "var(--btn-fg)",
              background: "var(--tx)",
              padding: "11px 24px",
              borderRadius: 9999,
              whiteSpace: "nowrap",
            }}
          >
            ابدأ التجربة المجانية
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer style={{ borderTop: "1px solid var(--line)", padding: "28px 28px 36px" }}>
      <div style={{ width: "min(1180px,100%)", margin: "0 auto", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, fontWeight: 600, fontSize: 15 }}>
          <BrandMark className="h-5 w-5" />
          ظهور
        </div>
        <div style={{ flex: 1 }} />
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 12,
            color: "var(--mut)",
            border: "1px solid var(--line)",
            borderRadius: 9999,
            padding: "6px 13px",
            whiteSpace: "nowrap",
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "#16a34a",
              animation: "rpulse 2.4s ease-in-out infinite",
            }}
          />
          جميع الأنظمة تعمل
        </div>
        <div style={{ fontSize: 12, color: "var(--dim)" }}>© ٢٠٢٦ ظهور. جميع الحقوق محفوظة.</div>
      </div>
    </footer>
  );
}
