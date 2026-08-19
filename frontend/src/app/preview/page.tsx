"use client";

import Link from "next/link";
import { type CSSProperties, type FormEvent, useEffect, useRef, useState } from "react";

import "../landing.css";
import {
  createPreviewReport,
  getPreviewReport,
  joinPreviewReportBeta,
  type PreviewQueryResult,
  type PreviewQuerySourceResult,
  type PreviewReportData,
} from "@/lib/api";

// طبقًا للمواصفات: خطوة واحدة لإدخال الرابط، انتظار واحد فقط، ثم شاشات
// النتيجة تُعرض جميعها من نفس اللقطة (report) المجلوبة مرة واحدة — لا يوجد
// أي طلب شبكة جديد بين الشاشات التالية. "welcome" تمهيد سريع لشرح ظهور،
// نفس بداية /signup القديمة، قبل خطوة إدخال الرابط.
const STEPS = [
  "welcome", "url", "waiting", "understanding", "visibility", "market", "competitors", "queries", "recommendation", "beta",
] as const;
type Step = (typeof STEPS)[number];

// رسائل تجميلية بحتة أثناء الانتظار — لا تتحكم أبدًا بالتنقل بين الشاشات،
// فقط تدور مع الوقت لإعطاء إحساس بالتقدّم.
const WAIT_MESSAGES = [
  "تعرّفنا على متجرك",
  "عرفنا وش تبيع",
  "جهزنا عمليات البحث",
  "بحثنا عنك",
  "قارناك بالمتاجر اللي تظهر معك",
  "نجهز نتيجتك...",
];
const WAIT_MESSAGE_INTERVAL_MS = 4500;
const POLL_INTERVAL_MS = 2500;

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
const solidBtn: CSSProperties = {
  border: 0,
  cursor: "pointer",
  background: "var(--tx)",
  color: "var(--btn-fg)",
  fontWeight: 600,
  fontSize: 14,
  padding: 13,
  borderRadius: 11,
  width: "100%",
};
const stepFooter: CSSProperties = { marginTop: 22, display: "flex", alignItems: "center", gap: 10 };
const backBtn: CSSProperties = {
  flexShrink: 0,
  height: 46,
  padding: "0 18px",
  borderRadius: 11,
  border: "1px solid var(--line)",
  background: "transparent",
  cursor: "pointer",
  color: "var(--mut)",
  fontSize: 13.5,
};
const captionNote: CSSProperties = { marginTop: 10, fontSize: 12, color: "var(--dim)", lineHeight: 1.8 };
const card: CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  borderRadius: 16,
  padding: 20,
};
const sectionTitle: CSSProperties = { margin: "22px 0 10px", fontSize: 15, fontWeight: 700 };

const PREVIEW_BYPASS_STORAGE_KEY = "zuhoor_preview_bypass";

// A one-time ?key=... link (shared privately with the site owner, never a
// visible UI control) lets repeated testing skip the per-IP cooldown
// backend enforces — see app.api.preview_reports._is_bypass. Persisted to
// localStorage on first use so the same browser keeps working without the
// query param on every later visit.
function getBypassToken(): string | null {
  if (typeof window === "undefined") return null;
  const fromUrl = new URLSearchParams(window.location.search).get("key");
  if (fromUrl && fromUrl.trim()) {
    window.localStorage.setItem(PREVIEW_BYPASS_STORAGE_KEY, fromUrl.trim());
    return fromUrl.trim();
  }
  return window.localStorage.getItem(PREVIEW_BYPASS_STORAGE_KEY);
}

function blurDomain(domain: string): string {
  const base = domain.split(".")[0] || domain;
  if (base.length <= 2) return `${base}••••`;
  return `${base.slice(0, 2)}${"•".repeat(Math.max(4, base.length - 2))}`;
}

// The merchant's own logo, preferring the crawler's extraction (og:image or
// a real <link rel="icon">, usually higher quality) and falling back to a
// public favicon service keyed off the domain if the crawl found nothing or
// the image fails to load — only falling back to a plain letter monogram if
// both real sources fail.
function StoreLogo({ domain, crawledLogo, brandName }: { domain: string; crawledLogo: string | null; brandName: string }) {
  const [stage, setStage] = useState<"crawled" | "favicon" | "letter">(crawledLogo ? "crawled" : "favicon");
  const src = stage === "crawled" ? crawledLogo! : `https://www.google.com/s2/favicons?sz=128&domain=${encodeURIComponent(domain)}`;
  if (stage === "letter") {
    return (
      <div style={{ width: 48, height: 48, borderRadius: 10, background: "var(--panel2)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: "var(--mut)" }}>
        {brandName.trim().charAt(0) || "؟"}
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- external store asset / favicon service, not our crawl pipeline
    <img
      src={src}
      alt=""
      width={48}
      height={48}
      style={{ borderRadius: 10, objectFit: "contain", background: "var(--panel2)" }}
      onError={() => setStage((s) => (s === "crawled" ? "favicon" : "letter"))}
    />
  );
}

// A competitor's real site icon, fetched from a public favicon service keyed
// off their domain (already known from search) and rendered blurred inside a
// circle — still shows a real, recognizable mark instead of a bare lock, but
// keeps the identity hidden until the merchant joins the beta.
function BlurredCompetitorMark({ domain }: { domain: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div style={{ position: "relative", width: 38, height: 38, flexShrink: 0 }}>
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: "50%",
          overflow: "hidden",
          background: "var(--panel2)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {!failed ? (
          // eslint-disable-next-line @next/next/no-img-element -- third-party favicon service, not our crawl pipeline
          <img
            src={`https://www.google.com/s2/favicons?sz=64&domain=${encodeURIComponent(domain)}`}
            alt=""
            onError={() => setFailed(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(3.5px)", transform: "scale(1.35)" }}
          />
        ) : (
          <span className="mono" style={{ fontSize: 13, fontWeight: 700, color: "var(--dim)", filter: "blur(1.5px)" }}>
            {(domain.trim().charAt(0) || "؟").toUpperCase()}
          </span>
        )}
      </div>
      <span
        aria-hidden
        style={{
          position: "absolute",
          bottom: -2,
          left: -2,
          width: 17,
          height: 17,
          borderRadius: "50%",
          background: "var(--panel)",
          border: "1px solid var(--line)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 9,
        }}
      >
        🔒
      </span>
    </div>
  );
}

// كل مصدر (Google/AI) له ثلاث حالات فقط، بلا تخمين أبدًا: نجاح مع ظهور،
// نجاح بدون ظهور، أو غير معروف (فشل تقني أو نتيجة غامضة) — لا نعرض أبدًا
// "لم يظهر" على عملية بحث لم تُنفَّذ فعليًا بنجاح.
function googleRow(source: PreviewQuerySourceResult): string {
  if (source.status !== "success") return "غير متاح";
  if (source.brand_found === true) return `#${source.position ?? 0}`;
  if (source.brand_found === false) return "ما ظهرت";
  return "بيانات غير كافية";
}

function aiRow(source: PreviewQuerySourceResult): string {
  if (source.status !== "success") return "غير متاح";
  if (source.brand_found === true) return "ذُكرت";
  if (source.brand_found === false) return "ما ذُكرت";
  return "بيانات غير كافية";
}

// ترتيب الفرص الضائعة أولًا (spec: الهدف من هذه الشاشة إظهار الفرص
// الضائعة لا استعراض أفضل النتائج) — 0: ظهور مؤكد بأنه لم يحدث، 1: بيانات
// غير كافية/فشل تقني، 2: ظهر فعليًا في أحد المصدرين.
function queryPriority(q: PreviewQueryResult): number {
  const confirmedMissing =
    (q.google.status === "success" && q.google.brand_found === false) ||
    (q.ai.status === "success" && q.ai.brand_found === false);
  const confirmedFound = q.google.brand_found === true || q.ai.brand_found === true;
  if (confirmedMissing) return 0;
  if (!confirmedFound) return 1;
  return 2;
}

type MarketStatus = {
  competitorCount: number;
  yourDisplay: string;
  avgDisplay: string;
  topDisplay: string;
  aheadCount: number | null;
  opportunityQueryCount: number;
};

// Aggregates the same competitors[]/queries[] the competitors/queries steps
// already render into a single "how do you compare" snapshot for the market
// step — no new backend computation, every number here is already present
// in the report payload (competitors[].visibility_percentage and
// competitors[].queries, both already sent to the client).
function computeMarketStatus(report: PreviewReportData): MarketStatus {
  const { visibility, competitors, queries } = report;

  const competitorPcts = competitors
    .map((c) => c.visibility_percentage)
    .filter((pct): pct is number => pct !== null);
  const avgCompetitorPct = competitorPcts.length
    ? Math.round(competitorPcts.reduce((sum, pct) => sum + pct, 0) / competitorPcts.length)
    : null;
  const topCompetitorPct = competitorPcts.length ? Math.max(...competitorPcts) : null;

  const yourPct = visibility.mode === "measured" ? visibility.score : null;

  // "أي منافس نسبته أعلى منك" only has a numeric meaning once we have a real
  // percentage for the store itself. With a confirmed-weak-but-unmeasured
  // sample (estimated/low) we still know competitors with any real presence
  // are ahead of it; with no usable sample at all (estimated/limited) we
  // can't honestly claim a comparison, so aheadCount stays null and the UI
  // skips that line rather than guessing.
  let yourDisplay: string;
  let aheadCount: number | null;
  if (yourPct !== null) {
    yourDisplay = `${yourPct}%`;
    aheadCount = competitorPcts.filter((pct) => pct > yourPct).length;
  } else if (visibility.mode === "estimated" && visibility.level === "low") {
    yourDisplay = "ضعيف";
    aheadCount = competitorPcts.filter((pct) => pct > 0).length;
  } else {
    yourDisplay = "غير كافٍ للقياس";
    aheadCount = null;
  }

  const competitorQuerySet = new Set(competitors.flatMap((c) => c.queries));
  const opportunityQueryCount = queries.filter((q) => {
    const youAppeared = q.google.brand_found === true || q.ai.brand_found === true;
    return !youAppeared && competitorQuerySet.has(q.query);
  }).length;

  return {
    competitorCount: competitors.length,
    yourDisplay,
    avgDisplay: avgCompetitorPct !== null ? `${avgCompetitorPct}%` : "—",
    topDisplay: topCompetitorPct !== null ? `${topCompetitorPct}%` : "—",
    aheadCount,
    opportunityQueryCount,
  };
}

function MarketStatRow({ label, value, strong, last }: { label: string; value: string; strong?: boolean; last?: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 14,
        padding: "12px 16px",
        borderBottom: last ? "none" : "1px solid var(--line)",
      }}
    >
      <span style={{ fontSize: 12.5, color: "var(--dim)" }}>{label}</span>
      <span className="mono" style={{ fontSize: strong ? 16 : 13, fontWeight: 700, color: strong ? "var(--acc)" : "var(--tx)" }}>
        {value}
      </span>
    </div>
  );
}

const REPORT_FEEDBACK_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "very_useful", label: "مفيد جدًا" },
  { value: "useful", label: "مفيد" },
  { value: "neutral", label: "عادي" },
  { value: "unclear", label: "ما كان واضح" },
  { value: "inaccurate", label: "النتائج ما كانت دقيقة" },
];

const INTEREST_LEVEL_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "very_interested", label: "مهتم جدًا" },
  { value: "interested", label: "مهتم" },
  { value: "might_try", label: "ممكن أجربه" },
  { value: "not_sure", label: "مو متأكد" },
  { value: "not_interested", label: "غير مهتم حاليًا" },
];

export default function PreviewPage() {
  const [stepIndex, setStepIndex] = useState(0);
  const step: Step = STEPS[stepIndex];

  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [reportId, setReportId] = useState<string | null>(null);
  const [reportStatus, setReportStatus] = useState<"processing" | "ready" | "failed">("processing");
  const [reportError, setReportError] = useState<string | null>(null);
  const [report, setReport] = useState<PreviewReportData | null>(null);
  const [messageIndex, setMessageIndex] = useState(0);

  const [betaModalOpen, setBetaModalOpen] = useState(false);
  const [leadName, setLeadName] = useState("");
  const [leadEmail, setLeadEmail] = useState("");
  const [leadFeedback, setLeadFeedback] = useState("");
  const [leadInterest, setLeadInterest] = useState("");
  const [leadSubmitting, setLeadSubmitting] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);
  const [leadSubmitted, setLeadSubmitted] = useState(false);

  const next = () => setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  const back = () => setStepIndex((i) => Math.max(i - 1, 0));

  const startAnalysisWithUrl = async (storeUrl: string) => {
    const trimmed = storeUrl.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await createPreviewReport(trimmed, getBypassToken());
      setReportId(res.report_id);
      setReportStatus("processing");
      setReportError(null);
      setMessageIndex(0);
      setStepIndex(2); // waiting
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "تعذّر بدء التحليل، حاول مرة أخرى");
    } finally {
      setSubmitting(false);
    }
  };

  const startAnalysis = (e: FormEvent) => {
    e.preventDefault();
    startAnalysisWithUrl(url);
  };

  // رابط الموقع الرئيسية يمرّر النطاق عبر ?domain=... — إن وُجد، يبدأ
  // التحليل تلقائيًا بدل مطالبة المستخدم بكتابته مرة ثانية (نفس سلوك
  // /signup السابق، DESIGN-1). autoStarted يمنع إنشاء تقريرين مكررين
  // بسبب التشغيل المزدوج لـ useEffect في React StrictMode أثناء التطوير.
  const autoStarted = useRef(false);
  useEffect(() => {
    if (autoStarted.current) return;
    const fromHomepage = new URLSearchParams(window.location.search).get("domain");
    if (fromHomepage && fromHomepage.trim()) {
      autoStarted.current = true;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setUrl(fromHomepage.trim());
      startAnalysisWithUrl(fromHomepage.trim());
    }
    // مرة واحدة فقط عند التحميل الأول.
  }, []);

  const retry = () => {
    setReportId(null);
    setReportStatus("processing");
    setReportError(null);
    setReport(null);
    setStepIndex(1); // رجوع لخطوة إدخال الرابط، لا الشاشة التمهيدية
  };

  useEffect(() => {
    if (step !== "waiting" || reportStatus !== "processing") return;
    const timer = setInterval(() => {
      setMessageIndex((i) => Math.min(i + 1, WAIT_MESSAGES.length - 1));
    }, WAIT_MESSAGE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [step, reportStatus]);

  useEffect(() => {
    if (step !== "waiting" || !reportId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const res = await getPreviewReport(reportId);
        if (disposed) return;
        if (res.status === "ready" && res.report) {
          setReport(res.report);
          setReportStatus("ready");
        } else if (res.status === "failed") {
          setReportStatus("failed");
          setReportError(res.error_message ?? "تعذّر إكمال التحليل");
        } else {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (!disposed) timer = setTimeout(poll, POLL_INTERVAL_MS * 2);
      }
    };
    poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [step, reportId]);

  const submitLead = async (e: FormEvent) => {
    e.preventDefault();
    if (!reportId) return;
    const name = leadName.trim();
    const email = leadEmail.trim();
    if (!name) {
      setLeadError("أدخل اسمك");
      return;
    }
    if (!email) {
      setLeadError("أدخل بريدك الإلكتروني");
      return;
    }
    if (!leadFeedback) {
      setLeadError("اختر تقييمك للتقرير");
      return;
    }
    if (!leadInterest) {
      setLeadError("اختر مدى اهتمامك");
      return;
    }
    setLeadSubmitting(true);
    setLeadError(null);
    try {
      await joinPreviewReportBeta(reportId, {
        name,
        email,
        report_feedback: leadFeedback,
        interest_level: leadInterest,
      });
      setLeadSubmitted(true);
    } catch (err) {
      setLeadError(err instanceof Error ? err.message : "تعذّر إرسال الطلب");
    } finally {
      setLeadSubmitting(false);
    }
  };

  const visibility = report?.visibility ?? null;
  const topCompetitorPct =
    report && report.competitors.length > 0
      ? Math.max(...report.competitors.map((c) => c.visibility_percentage ?? 0))
      : null;
  const marketStatus = report ? computeMarketStatus(report) : null;

  const showBack = stepIndex > 0 && step !== "waiting";
  const showDots = stepIndex >= 3;
  const dotSteps = STEPS.slice(3);
  const flowIndex = Math.max(0, stepIndex - 3);

  return (
    <div
      dir="rtl"
      className="rasid-landing rl-signup-grid"
      style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: "100vh", background: "var(--ink)" }}
    >
      <div style={{ position: "relative", display: "flex", flexDirection: "column", padding: "22px 28px 34px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 13.5, color: "var(--mut)" }}>
          <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: 7, color: "inherit" }}>
            <span style={{ fontSize: 14, lineHeight: 1 }}>‹]</span>خروج
          </Link>
        </div>

        <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
          <div
            key={step}
            style={{
              width: "100%",
              maxWidth: 460,
              minHeight: 500,
              margin: "0 auto",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              animation: "ofade .45s ease both",
            }}
          >
          {step === "welcome" && (
            <div>
              <h1 style={{ margin: 0, fontSize: "clamp(28px,3.4vw,38px)", fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1.3 }}>
                هل يجدك عملاؤك عندما يبحثون عن منتجاتك؟
              </h1>
              <p style={{ margin: "16px 0 0", fontSize: 14.5, color: "var(--mut)", lineHeight: 1.9 }}>
                حلّل متجرك واعرف أين يظهر، ومن يظهر بدلًا منه، وما الذي يمكنك تحسينه — بتحليل واحد سريع
              </p>
              <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 26, width: "auto", padding: "12px 24px" }}>
                حلّل متجري
              </button>
            </div>
          )}

          {step === "url" && (
            <form onSubmit={startAnalysis}>
              <h1 style={{ margin: 0, fontSize: 27, fontWeight: 600, letterSpacing: "-.02em" }}>
                خلنا نشوف كيف يظهر متجرك
              </h1>
              <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.8 }}>
                حط رابط متجرك والباقي علينا
              </p>
              <div style={fieldLabel}>رابط المتجر</div>
              <div
                dir="ltr"
                style={{
                  marginTop: 8, display: "flex", alignItems: "center", border: "1px solid var(--line)",
                  borderRadius: 11, background: "var(--panel)", overflow: "hidden",
                }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: 12.5, color: "var(--dim)", padding: "0 12px", borderRight: "1px solid var(--line)",
                    alignSelf: "stretch", display: "flex", alignItems: "center", background: "var(--panel2)",
                  }}
                >
                  https://
                </span>
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="example.com"
                  dir="ltr"
                  style={{ flex: 1, minWidth: 0, background: "transparent", border: 0, outline: "none", color: "var(--tx)", fontSize: 14, padding: 12, textAlign: "left" }}
                />
              </div>
              {submitError && <div style={{ marginTop: 10, fontSize: 12.5, color: "#dc4c4c" }}>{submitError}</div>}
              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button type="submit" disabled={submitting || !url.trim()} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1, opacity: submitting ? 0.7 : 1 }}>
                  {submitting ? "جاري البدء..." : "حلّل متجري"}
                </button>
              </div>
            </form>
          )}

          {step === "waiting" && (
            <div>
              {reportStatus === "failed" ? (
                <div>
                  <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>تعذّر تحليل متجرك</h1>
                  <p style={{ margin: "12px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.8 }}>
                    {reportError ?? "حدث خطأ غير متوقع أثناء التحليل"}
                  </p>
                  <button onClick={retry} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 22 }}>
                    حاول مرة أخرى
                  </button>
                </div>
              ) : reportStatus === "ready" ? (
                <div>
                  <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>تقريرك جاهز</h1>
                  <p style={{ margin: "12px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.8 }}>
                    فهمنا متجرك وبحثنا عنك — خلنا نوريك النتيجة
                  </p>
                  <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 22 }}>
                    شوف النتيجة
                  </button>
                </div>
              ) : (
                <div>
                  <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>نحلل متجرك الآن...</h1>
                  <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
                    {WAIT_MESSAGES.map((message, index) => (
                      <div
                        key={message}
                        style={{
                          display: "flex", alignItems: "center", gap: 10, fontSize: 14,
                          color: index <= messageIndex ? "var(--tx)" : "var(--dim)",
                          opacity: index <= messageIndex ? 1 : 0.5,
                          transition: "opacity .3s ease, color .3s ease",
                        }}
                      >
                        <span style={{ color: index < messageIndex ? "var(--acc)" : "var(--dim)" }}>
                          {index < messageIndex ? "✓" : "◌"}
                        </span>
                        {message}
                      </div>
                    ))}
                  </div>
                  <p style={captionNote}>هذا قد يأخذ نصف دقيقة تقريبًا</p>
                </div>
              )}
            </div>
          )}

          {step === "understanding" && report && (
            <div>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>فهمنا متجرك</h1>
              <div style={{ ...card, marginTop: 22, display: "flex", alignItems: "center", gap: 14 }}>
                <StoreLogo domain={report.store.domain} crawledLogo={report.store.logo} brandName={report.store.brand_name} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>{report.store.brand_name}</div>
                  <div className="mono" dir="ltr" style={{ fontSize: 12, color: "var(--dim)", marginTop: 2 }}>
                    {report.store.domain}
                  </div>
                </div>
              </div>
              <div style={{ ...card, marginTop: 14, padding: 0, overflow: "hidden" }}>
                {[
                  ["اسم المتجر", report.store.brand_name],
                  ["الرابط", report.store.domain],
                  ["الفئة", report.store.category || "—"],
                  ["وش تبيع", report.store.products.slice(0, 4).join("، ") || "—"],
                  ["أهم الفئات", report.store.categories.slice(0, 5).join("، ") || "—"],
                ].map(([label, value], i, arr) => (
                  <div
                    key={label}
                    style={{
                      display: "flex", justifyContent: "space-between", gap: 14, padding: "12px 16px",
                      borderBottom: i < arr.length - 1 ? "1px solid var(--line)" : "none",
                    }}
                  >
                    <span style={{ fontSize: 12.5, color: "var(--dim)", flexShrink: 0 }}>{label}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, textAlign: "left" }}>{value}</span>
                  </div>
                ))}
              </div>
              <p style={captionNote}>استخدمنا محتوى متجرك لتحديد عمليات البحث المناسبة لك</p>
              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}>
                  التالي: شوف وضع ظهورك
                </button>
              </div>
            </div>
          )}

          {step === "visibility" && report && visibility && (
            <div>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>وضع ظهورك</h1>

              {visibility.mode === "measured" ? (
                <>
                  <p style={{ margin: "14px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.9 }}>
                    هذا ظهور متجرك في عمليات البحث المرتبطة بمنتجاتك
                  </p>
                  <div style={{ ...card, marginTop: 16, textAlign: "center", padding: "30px 20px" }}>
                    <div style={{ fontSize: 52, fontWeight: 700, color: "var(--acc)", letterSpacing: "-.02em" }}>
                      {visibility.score !== null ? `${visibility.score}%` : "—"}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--mut)", marginTop: 6 }}>نسبة ظهورك</div>
                  </div>
                  {topCompetitorPct !== null && topCompetitorPct > (visibility.score ?? 0) && (
                    <div style={{ ...card, marginTop: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
                        <span>متجرك — {visibility.score ?? 0}%</span>
                        <span style={{ fontWeight: 700 }}>أعلى متجر ظهر — {topCompetitorPct}%</span>
                      </div>
                      <p style={{ margin: "10px 0 0", fontSize: 13, color: "var(--mut)", lineHeight: 1.8 }}>
                        بعض المتاجر تظهر أمام نفس العميل أكثر من متجرك بوضوح
                      </p>
                    </div>
                  )}
                  <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div style={{ ...card, textAlign: "center" }}>
                      <div style={{ fontSize: 12, color: "var(--dim)" }}>Google</div>
                      <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>
                        {visibility.google_score !== null ? `${visibility.google_score}%` : "—"}
                      </div>
                    </div>
                    <div style={{ ...card, textAlign: "center" }}>
                      <div style={{ fontSize: 12, color: "var(--dim)" }}>الذكاء الاصطناعي</div>
                      <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>
                        {visibility.ai_score !== null ? `${visibility.ai_score}%` : "—"}
                      </div>
                    </div>
                  </div>
                  <p style={{ marginTop: 16, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>
                    لما يبحث العميل عن منتجات مثل اللي تبيعها، متجرك يظهر تقريبًا في{" "}
                    {Math.round((visibility.brand_mentions / Math.max(visibility.successful_checks, 1)) * 10)}{" "}
                    من كل 10 عمليات بحث فحصناها
                  </p>
                </>
              ) : visibility.level === "low" ? (
                <>
                  <h2 style={{ margin: "16px 0 0", fontSize: 17, fontWeight: 700 }}>ظهور متجرك ضعيف حاليًا</h2>
                  <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>
                    ظهر متجرك بشكل محدود في عمليات البحث المرتبطة بالمنتجات والفئات اللي تبيعها
                  </p>
                  <div style={{ ...card, marginTop: 16, textAlign: "center", padding: "30px 20px" }}>
                    <div style={{ fontSize: 34, fontWeight: 700, color: "var(--acc)" }}>أقل من 50%</div>
                    <div style={{ fontSize: 13, color: "var(--mut)", marginTop: 6 }}>نسبة ظهورك</div>
                  </div>
                  <p style={{ marginTop: 16, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>
                    هذا يعني أن العميل لما يبحث عن منتجات مثل منتجاتك، متجرك ما يكون من الخيارات الظاهرة له في كثير
                    من الحالات
                  </p>
                  <p style={{ marginTop: 10, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>
                    وفي نفس عمليات البحث تظهر متاجر أخرى تنافس على نفس العميل، وهذا يعني أن عندك فرصة واضحة لزيادة
                    ظهور متجرك
                  </p>
                </>
              ) : (
                <>
                  <h2 style={{ margin: "16px 0 0", fontSize: 17, fontWeight: 700 }}>ظهورك محدود</h2>
                  <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>
                    ما قدرنا نجمع عينة كافية من نتائج بحث فعلية لمتجرك في هذا الفحص، فما نقدر نطلع لك نسبة دقيقة
                    الحين
                  </p>
                  <div style={{ ...card, marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: "var(--dim)", fontWeight: 600 }}>وش يعني هذا؟</div>
                    <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--mut)", lineHeight: 1.8 }}>
                      هذا شائع لما يكون وصف منتجات المتجر مختصر جدًا، أو لما تواجه عمليات البحث ضغطًا مؤقتًا وقت
                      الفحص — مو انعكاس لسوء ظهور متجرك فعليًا
                    </p>
                  </div>
                  <p style={{ marginTop: 14, fontSize: 13, color: "var(--mut)", lineHeight: 1.8 }}>
                    النسخة التجريبية تعيد فحص متجرك باستمرار وتقيس ظهورك بدقة أكبر مع الوقت
                  </p>
                </>
              )}

              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}>
                  التالي: وضع السوق
                </button>
              </div>
            </div>
          )}

          {step === "market" && report && marketStatus && (
            <div>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>وضع السوق</h1>

              {marketStatus.competitorCount === 0 ? (
                <p style={{ margin: "18px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.9 }}>
                  ما لقينا سوق منافس واضح لمتجرك في عمليات البحث اللي فحصناها
                </p>
              ) : (
                <>
                  <h2 style={sectionTitle}>موقعك في السوق</h2>
                  <div style={{ ...card, padding: 0, overflow: "hidden" }}>
                    <MarketStatRow label="ظهور متجرك" value={marketStatus.yourDisplay} strong />
                    <MarketStatRow label="متوسط المتاجر المشابهة" value={marketStatus.avgDisplay} />
                    <MarketStatRow label="أعلى متجر" value={marketStatus.topDisplay} last />
                  </div>

                  <h2 style={sectionTitle}>المنافسة على الظهور</h2>
                  <div style={card}>
                    <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.9 }}>
                      <b className="mono">{marketStatus.competitorCount}</b> متاجر تتنافس معك على نفس عمليات البحث
                    </p>
                    {marketStatus.aheadCount !== null && (
                      <p style={{ margin: "8px 0 0", fontSize: 13.5, lineHeight: 1.9 }}>
                        <b className="mono">{marketStatus.aheadCount}</b> منها تظهر أكثر منك بشكل واضح
                      </p>
                    )}
                  </div>

                  <h2 style={sectionTitle}>أكبر فرصة لك</h2>
                  <div style={{ ...card, background: "rgba(14,157,134,.08)", border: "1px solid rgba(14,157,134,.25)" }}>
                    {marketStatus.opportunityQueryCount > 0 ? (
                      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.9 }}>
                        هناك <b className="mono">{marketStatus.opportunityQueryCount}</b> عملية بحث مرتبطة بمنتجاتك يظهر فيها منافسون ولا تظهر علامتك
                      </p>
                    ) : (
                      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.9 }}>
                        ما لقينا عمليات بحث ظهر فيها منافس بشكل مؤكد وما ظهرت فيها أنت
                      </p>
                    )}
                  </div>
                </>
              )}

              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}>
                  التالي: شوف المنافسين
                </button>
              </div>
            </div>
          )}

          {step === "competitors" && report && (
            <div>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>لقينا مين يظهر معك وبدالك</h1>
              {report.competitors.length > 0 ? (
                <>
                  <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.8 }}>
                    لقينا متاجر تتكرر في نفس عمليات البحث اللي تخص المنتجات اللي تبيعها
                  </p>
                  <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 10 }}>
                    {report.competitors.slice(0, 3).map((c) => (
                      <div key={c.domain} style={{ ...card, display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}>
                        <BlurredCompetitorMark domain={c.domain} />
                        <span style={{ flex: 1, fontSize: 14, fontWeight: 600 }}>{blurDomain(c.domain)}</span>
                        <span style={{ fontSize: 13, color: "var(--mut)" }}>
                          {c.visibility_percentage !== null ? `${c.visibility_percentage}%` : "—"}
                        </span>
                      </div>
                    ))}
                    {report.competitors.length > 3 && (
                      <div style={{ fontSize: 13, color: "var(--dim)", textAlign: "center", padding: "4px 0" }}>
                        + {report.competitors.length - 3} متاجر أخرى
                      </div>
                    )}
                  </div>
                  <p style={captionNote}>🔒 أسماء المنافسين كاملة ضمن التقرير الكامل بعد الانضمام للنسخة التجريبية</p>
                </>
              ) : (
                <p style={{ margin: "18px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.9 }}>
                  ما ظهر متجر واحد بشكل متكرر كفاية في هذا الفحص
                </p>
              )}
              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}>
                  التالي: شوف عمليات البحث
                </button>
              </div>
            </div>
          )}

          {step === "queries" && report && (
            <div>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>هذه الأشياء اللي يبحث عنها عميلك</h1>
              <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
                فحصنا ظهور متجرك في عمليات البحث المرتبطة بما تبيع
              </p>
              <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8, maxHeight: 420, overflowY: "auto" }}>
                {[...report.queries]
                  .sort((a, b) => queryPriority(a) - queryPriority(b))
                  .map((q) => (
                    <div key={q.query} style={{ ...card, padding: "12px 14px" }}>
                      <div style={{ fontSize: 13.5 }}>{q.query}</div>
                      <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--dim)" }}>
                          <span>Google</span>
                          <span className="mono">{googleRow(q.google)}</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--dim)" }}>
                          <span>الذكاء الاصطناعي</span>
                          <span className="mono">{aiRow(q.ai)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}>
                  التالي: التوصية
                </button>
              </div>
            </div>
          )}

          {step === "recommendation" && report && (
            <div>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>أول شيء ننصحك تسويه</h1>
              <div style={{ ...card, marginTop: 22 }}>
                <div style={{ fontSize: 16, fontWeight: 700 }}>{report.recommendation.title}</div>
                <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.9 }}>
                  {report.recommendation.reason}
                </p>
                {report.recommendation.evidence.length > 0 && (
                  <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                    {report.recommendation.evidence.map((q) => (
                      <div
                        key={q}
                        style={{ fontSize: 12.5, color: "var(--tx)", background: "var(--panel2)", borderRadius: 8, padding: "8px 10px" }}
                      >
                        {q}
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line)" }}>
                  <div style={{ fontSize: 12, color: "var(--dim)", fontWeight: 600 }}>وش تسوي؟</div>
                  <p style={{ margin: "6px 0 0", fontSize: 13.5, lineHeight: 1.9 }}>{report.recommendation.action}</p>
                </div>
              </div>
              <p style={captionNote}>🔒 التقرير الكامل يتضمن توصيات إضافية لمتجرك</p>
              <div style={stepFooter}>
                {showBack && (
                  <button type="button" onClick={back} style={backBtn}>
                    رجوع
                  </button>
                )}
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}>
                  باقي التقرير جاهز لك
                </button>
              </div>
            </div>
          )}

          {step === "beta" && (
            <div>
              {leadSubmitted ? (
                <div>
                  <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>تم! وصلنا طلبك</h1>
                  <p style={{ margin: "12px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.9 }}>
                    راح نتواصل معك قريبًا لتفعيل تقريرك الكامل
                  </p>
                </div>
              ) : (
                <div>
                  <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>باقي التقرير جاهز لك</h1>
                  <p style={{ margin: "12px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.9 }}>
                    اللي شفته مجرد جزء من الصورة. في النسخة التجريبية نفتح لك التفاصيل ونستمر نتابع ظهور متجرك
                  </p>
                  <div style={{ ...card, marginTop: 18 }}>
                    <div style={{ fontSize: 12.5, color: "var(--dim)", fontWeight: 600 }}>وش تحصل عليه؟</div>
                    <ul style={{ margin: "12px 0 0", padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 12 }}>
                      {[
                        ["أسماء المنافسين كاملة", "تعرف مين يظهر بدالك وكم مرة"],
                        ["كل عمليات البحث وتفاصيل ظهورك", "تشوف وين يظهر متجرك ووين تضيع الفرصة"],
                        ["توصيات إضافية خاصة بمتجرك", "خطوات مبنية على المشاكل اللي وجدناها فعلًا"],
                        ["متابعة ظهورك في Google والذكاء الاصطناعي", "بدل فحص واحد، نتابع ظهور متجرك باستمرار"],
                        ["تعرف هل ظهورك يتحسن", "تشوف كيف تتغير النتيجة مع الوقت وبعد التعديلات اللي تسويها"],
                      ].map(([title, desc]) => (
                        <li key={title} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                          <span style={{ color: "var(--acc)", flexShrink: 0 }}>✓</span>
                          <div>
                            <div style={{ fontSize: 13.5, fontWeight: 600 }}>{title}</div>
                            <div style={{ fontSize: 12.5, color: "var(--mut)", marginTop: 2, lineHeight: 1.7 }}>{desc}</div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div style={stepFooter}>
                    {showBack && (
                      <button type="button" onClick={back} style={backBtn}>
                        رجوع
                      </button>
                    )}
                    <button
                      onClick={() => setBetaModalOpen(true)}
                      className="rl-fill-soft"
                      style={{ ...solidBtn, marginTop: 0, width: "auto", flex: 1 }}
                    >
                      انضم للنسخة التجريبية
                    </button>
                  </div>
                  <p style={captionNote}>بدون بطاقة ائتمان · بدون دفع الآن</p>
                </div>
              )}
            </div>
          )}
          </div>
        </div>

        {showDots && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            {dotSteps.map((s, i) => (
              <span
                key={s}
                style={{
                  height: 4,
                  borderRadius: 9999,
                  background: i <= flowIndex ? "var(--tx)" : "var(--line)",
                  width: i === flowIndex ? 26 : 4,
                  transition: "all .3s ease",
                }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="rl-signup-image" style={{ position: "relative", overflow: "hidden", background: "var(--panel)" }}>
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: "url('/landing/city-map.jpg')",
            backgroundSize: "cover",
            backgroundPosition: "center",
            filter: "var(--map-filter)",
          }}
        />
        <div aria-hidden style={{ position: "absolute", inset: 0, background: "var(--veil)" }} />
        <div style={{ position: "absolute", inset: "auto 24px 24px 24px", color: "var(--tx)" }}>
          <div style={{ fontSize: 13, color: "var(--mut)", lineHeight: 1.9 }}>
            ظهور يحلّل ظهور متجرك في نتائج البحث ونتائج الذكاء الاصطناعي — ويخبرك من يظهر بدلًا منك
          </div>
        </div>
      </div>

      {betaModalOpen && !leadSubmitted && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,.55)", display: "flex",
            alignItems: "center", justifyContent: "center", padding: 20, zIndex: 50,
          }}
          onClick={() => !leadSubmitting && setBetaModalOpen(false)}
        >
          <form
            onSubmit={submitLead}
            onClick={(e) => e.stopPropagation()}
            style={{
              ...card, width: "100%", maxWidth: 420, maxHeight: "85vh", padding: 0,
              display: "flex", flexDirection: "column", overflow: "hidden",
            }}
          >
            <div style={{ padding: "20px 24px 4px", flexShrink: 0 }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>انضم للنسخة التجريبية</h2>
            </div>

            <div style={{ padding: "0 24px", overflowY: "auto", flex: 1, minHeight: 0 }}>
              <div style={{ ...fieldLabel, marginTop: 14 }}>الاسم</div>
              <input
                value={leadName}
                onChange={(e) => setLeadName(e.target.value)}
                placeholder="اسمك"
                style={textInput}
              />

              <div style={fieldLabel}>البريد الإلكتروني</div>
              <input
                type="email"
                value={leadEmail}
                onChange={(e) => setLeadEmail(e.target.value)}
                placeholder="you@example.com"
                dir="ltr"
                style={{ ...textInput, textAlign: "left" }}
              />

              <div style={fieldLabel}>كيف كان التقرير بالنسبة لك؟</div>
              <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {REPORT_FEEDBACK_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    style={{
                      display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, cursor: "pointer",
                      padding: "7px 9px", borderRadius: 9, border: "1px solid var(--line)",
                      background: leadFeedback === opt.value ? "var(--panel2)" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name="report_feedback"
                      value={opt.value}
                      checked={leadFeedback === opt.value}
                      onChange={() => setLeadFeedback(opt.value)}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>

              <div style={fieldLabel}>قد إيش مهتم تستخدم ظهور لمتابعة متجرك؟</div>
              <div style={{ marginTop: 8, marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {INTEREST_LEVEL_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    style={{
                      display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, cursor: "pointer",
                      padding: "7px 9px", borderRadius: 9, border: "1px solid var(--line)",
                      background: leadInterest === opt.value ? "var(--panel2)" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name="interest_level"
                      value={opt.value}
                      checked={leadInterest === opt.value}
                      onChange={() => setLeadInterest(opt.value)}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            <div style={{ padding: "12px 24px 20px", borderTop: "1px solid var(--line)", flexShrink: 0 }}>
              {leadError && <div style={{ marginBottom: 10, fontSize: 12.5, color: "#dc4c4c" }}>{leadError}</div>}
              <button
                type="submit"
                disabled={leadSubmitting}
                className="rl-fill-soft"
                style={{ ...solidBtn, opacity: leadSubmitting ? 0.7 : 1 }}
              >
                {leadSubmitting ? "جاري الإرسال..." : "أرسل طلبي"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
