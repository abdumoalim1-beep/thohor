"use client";

import Link from "next/link";
import { type CSSProperties, useEffect, useState } from "react";

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
          <a href="#features" style={{ color: "inherit" }}>المشكلة</a>
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

type PlatformIconName = "search" | "chat" | "assistant" | "social" | "article" | "news" | "video" | "forum";

// Generic representative marks for "search engines / AI chat / AI
// assistants / social platforms" — deliberately not reproductions of any
// specific brand's logo (trademark risk), just enough visual variety to
// read as "different platforms" at a glance, in our own line-icon style.
function PlatformIcon({ name }: { name: PlatformIconName }) {
  const common = { width: "100%", height: "100%", viewBox: "0 0 24 24", fill: "none" as const };
  const s = { stroke: "var(--acc)", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "search":
      return (
        <svg {...common}>
          <circle cx="10.5" cy="10.5" r="6.5" {...s} />
          <path d="M19.5 19.5l-4.3-4.3" {...s} />
        </svg>
      );
    case "chat":
      return (
        <svg {...common}>
          <rect x="3" y="4.5" width="18" height="11.5" rx="4" {...s} />
          <path d="M8 20l2.5-4" {...s} />
        </svg>
      );
    case "assistant":
      return (
        <svg {...common}>
          <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" {...s} strokeLinejoin="round" />
        </svg>
      );
    case "social":
      return (
        <svg {...common}>
          <circle cx="12" cy="8.2" r="3.2" {...s} />
          <path d="M5 19c0-3.4 3-5.5 7-5.5s7 2.1 7 5.5" {...s} />
        </svg>
      );
    case "article":
      return (
        <svg {...common}>
          <rect x="5" y="3.5" width="14" height="17" rx="2" {...s} />
          <path d="M8.3 8h7.4M8.3 12h7.4M8.3 16h4.5" {...s} />
        </svg>
      );
    case "news":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" {...s} />
          <path d="M12 3.5c-2.6 2.3-4 5.3-4 8.5s1.4 6.2 4 8.5c2.6-2.3 4-5.3 4-8.5s-1.4-6.2-4-8.5z" {...s} />
          <path d="M3.5 12h17" {...s} />
        </svg>
      );
    case "video":
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="14" rx="3" {...s} />
          <path d="M10 9.3l5 2.7-5 2.7V9.3z" {...s} strokeLinejoin="round" fill="var(--acc)" />
        </svg>
      );
    case "forum":
      return (
        <svg {...common}>
          <path d="M4 6.5h13a2 2 0 0 1 2 2V14a2 2 0 0 1-2 2H10l-4 3.5V16H4a2 2 0 0 1-2-2V8.5a2 2 0 0 1 2-2z" {...s} strokeLinejoin="round" />
        </svg>
      );
  }
}

// A short dashed line into a downward chevron — the "many things feed
// into one" connector reused wherever a panel needs to show convergence
// (row 1: one question -> platforms; row 3: sources -> one answer).
function DownConnector() {
  return (
    <div aria-hidden style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
      <span style={{ width: 1.5, height: 14, background: "var(--line)" }} />
      <svg width="14" height="8" viewBox="0 0 14 8" fill="none">
        <path d="M1 1l6 6 6-6" stroke="var(--dim)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// A single result row inside the card-1 "search" scene — solid for a
// real result, dashed+faded for the merchant's own missing listing.
function SearchResultRow({ label, muted }: { label: string; muted?: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "9px 12px",
        borderRadius: 10,
        border: muted ? "1px dashed var(--line)" : "1px solid var(--line)",
        background: muted ? "transparent" : "var(--panel)",
        opacity: muted ? 0.6 : 1,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: muted ? "var(--line)" : "var(--acc)", flexShrink: 0 }} />
      <span style={{ fontSize: 12.5, color: muted ? "var(--dim)" : "var(--tx)" }}>{label}</span>
    </div>
  );
}

// A single ranking row inside the card-2 "ranking" scene.
function RankRow({ rank, name, pct, strong, muted }: { rank: string; name: string; pct: string; strong?: boolean; muted?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, opacity: muted ? 0.65 : 1 }}>
      <span
        className="mono"
        style={{
          width: 26,
          height: 26,
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11.5,
          fontWeight: 700,
          flexShrink: 0,
          background: strong ? "var(--acc)" : "var(--panel)",
          border: strong ? "none" : "1px solid var(--line)",
          color: strong ? "#fff" : "var(--mut)",
        }}
      >
        {rank}
      </span>
      <span style={{ flex: 1, fontSize: 12.5, fontWeight: strong ? 600 : 400 }}>{name}</span>
      <span className="mono" style={{ fontSize: 11.5, fontWeight: 700, color: strong ? "var(--acc)" : "var(--dim)" }}>{pct}</span>
    </div>
  );
}

function Features() {
  const card: CSSProperties = {
    border: "1px solid var(--line)",
    borderRadius: 24,
    background: "var(--panel)",
    boxShadow: "0 20px 50px rgba(17,24,39,.08)",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  };
  const h3: CSSProperties = { margin: "12px 0 0", fontSize: 19, fontWeight: 600, letterSpacing: "-.01em", lineHeight: 1.35 };
  const body: CSSProperties = { margin: "8px 0 0", fontSize: 13.5, lineHeight: 1.8, color: "var(--mut)" };
  const visualWrap: CSSProperties = { marginTop: "auto", background: "var(--panel2)", padding: "24px 22px 26px" };

  const engines: { label: string; icon: PlatformIconName; mention: string }[] = [
    { label: "Google", icon: "search", mention: "منافس أ" },
    { label: "ChatGPT", icon: "assistant", mention: "منافس ب" },
    { label: "Gemini", icon: "chat", mention: "منافس أ" },
    { label: "Perplexity", icon: "social", mention: "منافس ج" },
  ];

  return (
    <section id="features" style={{ padding: "48px 28px 60px" }}>
      <div style={{ width: "min(1180px,100%)", margin: "0 auto", textAlign: "center" }}>
        <div className="mono" style={{ fontSize: 11, letterSpacing: ".16em", color: "var(--acc)" }}>01 — المشكلة</div>
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
          إدارة ظهورك في الذكاء الاصطناعي معقدة ومجزأة
        </h2>
        <p style={{ margin: "14px auto 0", maxWidth: 520, fontSize: 14.5, lineHeight: 1.85, color: "var(--mut)" }}>
          تضيع وقتك بين أدوات متفرقة، ومع ذلك لا تعرف أين تقف.
        </p>

        <div style={{ marginTop: 48, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 26, textAlign: "right" }}>
          {/* 1 — عملاؤك لا يجدونك: a real query, real results, your own listing absent */}
          <div style={card}>
            <div style={{ padding: "24px 24px 4px" }}>
              <h3 style={h3}>عملاؤك لا يجدونك</h3>
              <p style={body}>تظهر أقل في عمليات البحث التي تقود العملاء لمنتجاتك.</p>
            </div>
            <div style={visualWrap}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  background: "var(--panel)",
                  border: "1px solid var(--line)",
                  borderRadius: 9999,
                  padding: "10px 14px",
                  fontSize: 12.5,
                  color: "var(--tx)",
                }}
              >
                <span style={{ width: 15, height: 15, flexShrink: 0 }}>
                  <PlatformIcon name="search" />
                </span>
                أفضل متجر للعناية بالبشرة؟
              </div>
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                <SearchResultRow label="متجر العناية الفاخر" />
                <SearchResultRow label="بيوتي كلينك" />
                <SearchResultRow label="متجرك — غير موجود" muted />
              </div>
            </div>
          </div>

          {/* 2 — منافسوك يسبقونك: a ranking list, your row low and faded */}
          <div style={card}>
            <div style={{ padding: "24px 24px 4px" }}>
              <h3 style={h3}>منافسوك يسبقونك</h3>
              <p style={body}>يظهرون في الأسئلة المهمة، وأنت لا تعرف لماذا.</p>
            </div>
            <div style={visualWrap}>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <RankRow rank="١" name="منافس أ" pct="٪82" strong />
                <RankRow rank="٢" name="منافس ب" pct="٪61" />
                <RankRow rank="٧" name="متجرك" pct="٪28" muted />
              </div>
            </div>
          </div>

          {/* 3 — البحث لم يعد Google فقط: one question branching to 4 engines, none mentioning you */}
          <div style={card}>
            <div style={{ padding: "24px 24px 4px" }}>
              <h3 style={h3}>البحث لم يعد Google فقط</h3>
              <p style={body}>عملاؤك يسألون ChatGPT ومحركات الذكاء الاصطناعي قبل الشراء.</p>
            </div>
            <div style={visualWrap}>
              <div style={{ textAlign: "center" }}>
                <span
                  style={{
                    display: "inline-block",
                    fontSize: 12,
                    color: "var(--tx)",
                    background: "var(--panel)",
                    border: "1px solid var(--line)",
                    borderRadius: 9999,
                    padding: "8px 14px",
                  }}
                >
                  وين أشتري منتج عناية أصلي؟
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "center", marginTop: 10 }}>
                <DownConnector />
              </div>
              <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
                {engines.map((e) => (
                  <div
                    key={e.label}
                    style={{
                      background: "var(--panel)",
                      border: "1px solid var(--line)",
                      borderRadius: 12,
                      padding: "10px 6px",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 5,
                    }}
                  >
                    <span style={{ width: 18, height: 18 }}>
                      <PlatformIcon name={e.icon} />
                    </span>
                    <span style={{ fontSize: 9.5, fontWeight: 600 }}>{e.label}</span>
                    <span style={{ fontSize: 8.5, color: "var(--dim)" }}>{e.mention}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

type OrbitIconName =
  | "questions"
  | "visibility"
  | "answers"
  | "citations"
  | "competitors"
  | "content"
  | "publish"
  | "reports";

function OrbitIcon({ name }: { name: OrbitIconName }) {
  const common = { width: "100%", height: "100%", viewBox: "0 0 24 24", fill: "none" as const };
  const stroke = { stroke: "var(--acc)", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "questions":
      return (
        <svg {...common}>
          <rect x="3" y="4.5" width="18" height="11.5" rx="4" {...stroke} />
          <path d="M8 20l2.5-4" {...stroke} />
          <circle cx="8.2" cy="10.2" r="1" fill="var(--acc)" />
          <circle cx="12" cy="10.2" r="1" fill="var(--acc)" />
          <circle cx="15.8" cy="10.2" r="1" fill="var(--acc)" />
        </svg>
      );
    case "visibility":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" {...stroke} />
          <circle cx="12" cy="12" r="4.3" {...stroke} />
          <circle cx="12" cy="12" r="1.2" fill="var(--acc)" />
        </svg>
      );
    case "answers":
      return (
        <svg {...common}>
          <rect x="4.6" y="12" width="3.4" height="7" rx="1" {...stroke} />
          <rect x="10.3" y="8" width="3.4" height="11" rx="1" {...stroke} />
          <rect x="16" y="4.5" width="3.4" height="14.5" rx="1" {...stroke} />
        </svg>
      );
    case "citations":
      return (
        <svg {...common}>
          <path d="M8.5 8c-2.2 0-3.9 1.8-3.9 4v3.5h3.9V12H6.7c0-1.2.9-2.1 1.8-2.1V8z" {...stroke} strokeLinejoin="round" />
          <path d="M17.4 8c-2.2 0-3.9 1.8-3.9 4v3.5h3.9V12h-1.8c0-1.2.9-2.1 1.8-2.1V8z" {...stroke} strokeLinejoin="round" />
        </svg>
      );
    case "competitors":
      return (
        <svg {...common}>
          <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" {...stroke} />
          <circle cx="12" cy="12" r="2.7" {...stroke} />
        </svg>
      );
    case "content":
      return (
        <svg {...common}>
          <path d="M4.5 19.5l1-4.6L14.7 5.7l3.6 3.6-9.2 9.2-4.6 1z" {...stroke} />
          <path d="M13.2 7.2l3.6 3.6" {...stroke} />
        </svg>
      );
    case "publish":
      return (
        <svg {...common}>
          <path d="M3 12L20 4l-8 17-2.7-6.3L3 12z" {...stroke} strokeLinejoin="round" />
        </svg>
      );
    case "reports":
      return (
        <svg {...common}>
          <rect x="4" y="5.5" width="16" height="14.5" rx="2.5" {...stroke} />
          <path d="M4 9.5h16" {...stroke} />
          <path d="M8 3.5v4M16 3.5v4" {...stroke} />
        </svg>
      );
  }
}

function Solution() {
  // 8 items on a circle, 45° apart starting from the top — positions
  // pre-computed (θ=0° at top, clockwise) so no client-side layout math
  // is needed to place them.
  const items: { label: string; icon: OrbitIconName; top: string; left: string }[] = [
    { label: "رصد الأسئلة", icon: "questions", top: "8%", left: "50%" },
    { label: "قياس الظهور", icon: "visibility", top: "20.3%", left: "79.7%" },
    { label: "تحليل الإجابات", icon: "answers", top: "50%", left: "92%" },
    { label: "تتبّع الاستشهادات", icon: "citations", top: "79.7%", left: "79.7%" },
    { label: "مراقبة المنافسين", icon: "competitors", top: "92%", left: "50%" },
    { label: "توليد المحتوى", icon: "content", top: "79.7%", left: "20.3%" },
    { label: "النشر إلى موقعك", icon: "publish", top: "50%", left: "8%" },
    { label: "تقارير أسبوعية", icon: "reports", top: "20.3%", left: "20.3%" },
  ];

  // translate(-50%,-50%) centers the card on its top/left orbit point —
  // kept on a static outer wrapper, never animated, so the per-card
  // float/fade animation (on the inner element below) can set its own
  // `transform` in keyframes without clobbering this centering offset
  // (nested transforms compose; a shared one on the same element doesn't).
  const cellOuter: CSSProperties = { position: "absolute", display: "inline-block", transform: "translate(-50%,-50%)" };
  const cell: CSSProperties = {
    border: "1px solid var(--line)",
    borderRadius: 16,
    background: "var(--panel)",
    boxShadow: "0 4px 14px rgba(17,24,39,.06)",
    display: "inline-flex",
    flexDirection: "column",
    alignItems: "center",
  };

  return (
    <section id="solution" style={{ padding: "0 28px 60px" }}>
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
          كل ما تحتاجه للظهور، في مكان واحد
        </h2>
        <p style={{ margin: "14px auto 0", maxWidth: 540, fontSize: 14.5, lineHeight: 1.85, color: "var(--mut)" }}>
          من رصد الأسئلة إلى نشر المحتوى الذي يرفع ظهورك — دون أدوات متفرقة.
        </p>

        <div
          style={{
            position: "relative",
            width: "min(560px,92vw)",
            aspectRatio: "1 / 1",
            margin: "56px auto 0",
          }}
        >
          {/* dashed orbit path — slow continuous rotation for ambient motion */}
          <div
            aria-hidden
            style={{
              position: "absolute",
              inset: "8%",
              borderRadius: "50%",
              border: "1.5px dashed var(--line)",
              animation: "rspin 60s linear infinite",
            }}
          />

          {/* pulsing rings behind the center mark */}
          <div
            aria-hidden
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              width: 120,
              height: 120,
              transform: "translate(-50%,-50%)",
              pointerEvents: "none",
            }}
          >
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: "50%",
                  background: "radial-gradient(circle, rgba(14,157,134,.32) 0%, rgba(14,157,134,0) 70%)",
                  animation: `rping 3s ${i * 1}s ease-out infinite`,
                }}
              />
            ))}
          </div>

          {/* center — ظهور itself */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%,-50%)",
              zIndex: 2,
              padding: "18px 26px",
              border: "1px solid var(--line)",
              borderRadius: 22,
              background: "var(--panel)",
              boxShadow: "0 10px 30px rgba(14,157,134,.18)",
              display: "inline-flex",
              alignItems: "center",
              gap: 10,
              whiteSpace: "nowrap",
            }}
          >
            <BrandMark className="h-7 w-7" />
            <span style={{ fontSize: 19, fontWeight: 600 }}>ظهور</span>
          </div>

          {items.map((item, i) => (
            <div key={item.label} style={{ ...cellOuter, top: item.top, left: item.left, zIndex: 1 }}>
              <div
                className="rl-orbit-item"
                style={{
                  ...cell,
                  animation: `ofade .5s ${i * 0.06}s ease both, rfa ${6 + (i % 3)}s ${i * 0.3 + 0.5}s ease-in-out infinite`,
                }}
              >
                <span
                  className="rl-orbit-item-icon"
                  style={{ borderRadius: 10, background: "rgba(14,157,134,.12)", display: "flex", alignItems: "center", justifyContent: "center", padding: 5 }}
                >
                  <OrbitIcon name={item.icon} />
                </span>
                <span className="rl-orbit-item-label" style={{ fontWeight: 600, textAlign: "center", lineHeight: 1.4 }}>{item.label}</span>
              </div>
            </div>
          ))}
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
