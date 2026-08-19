"use client";

import Link from "next/link";
import { type CSSProperties, type Dispatch, type FormEvent, type ReactNode, type SetStateAction, useEffect, useState } from "react";

import "../landing.css";
import {
  confirmStoreBrandName,
  createOnboardingLead,
  createStore,
  getLatestVisibilityRun,
  getStoreUnderstanding,
  postCompetitorConfirmation,
  triggerResearchRun,
  triggerVisibilityRun,
  type StoreUnderstanding,
  type SuggestedCompetitorItem,
  type VisibilityRunDetail,
} from "@/lib/api";
import { arDigits } from "@/lib/visibility-score";

// عمليات البحث الفعلية على ChatGPT وGoogle تُدمج دائمًا في رقم واحد باسم
// موحّد "ظهور علامتك" — لا يظهر للمستخدم أي فرق بين المصدرين، ولا أي
// مصطلح تقني (محرك، Prompt، SERP...). التفاصيل التقنية تبقى في القاعدة
// فقط لأغراض التدقيق الداخلي.
//
// رحلتان ظاهرتان فقط: (1) التعرف على المتجر — welcome..brand؛ (2) تحليل
// ظهور العلامة — analyzing (شاشة تقدّم موحّدة واحدة، بلا مراحل فرعية
// ظاهرة) ثم شاشات التقرير (result..join)، وكلها جزء من نفس رحلة النتائج
// المتصلة، لا Dashboard منفصلة.
//
// تحليل الظهور يبدأ تلقائيًا فور اكتمال التعرف على المتجر (في خلفية شاشة
// brand، دون أي زر يبدأه صراحةً) — قرار مُراجَع بعد اختبار حي: انتظاران
// متتاليان (تعرّف ثم زر "متابعة" يبدأ انتظارًا ثانيًا من الصفر) شعر
// كتوقّفين منفصلين. بدء التحليل مبكرًا يجعل عداد "تم تحليل X من ٩٠" يبدأ
// من رقم متقدّم غالبًا بدل الصفر بحلول وصول المستخدم إليه.
const STEPS = [
  "welcome", "url", "scan", "brand",
  "analyzing", "result", "competitors", "search", "citations", "recommendations", "join",
] as const;
type Step = (typeof STEPS)[number];

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
const stepNavRow: CSSProperties = { marginTop: 22, display: "flex", alignItems: "center", gap: 14 };
const backLink: CSSProperties = { border: 0, background: "transparent", cursor: "pointer", color: "var(--mut)", fontSize: 13.5 };
const nextBtn: CSSProperties = {
  border: "1px solid var(--line)",
  cursor: "pointer",
  background: "var(--panel)",
  color: "var(--tx)",
  fontWeight: 600,
  fontSize: 13.5,
  padding: "11px 20px",
  borderRadius: 11,
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
};
const captionNote: CSSProperties = { marginTop: 10, fontSize: 12, color: "var(--dim)", lineHeight: 1.8 };
const secondaryLink: CSSProperties = { fontSize: 12.5, color: "var(--mut)", textAlign: "center", display: "block", marginTop: 12 };

export default function SignupPage() {
  const [dark, setDark] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  const [domain, setDomain] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [storeId, setStoreId] = useState<string | null>(null);
  const [scanAttempt, setScanAttempt] = useState(0);

  const [understanding, setUnderstanding] = useState<StoreUnderstanding | null>(null);
  const [brandEditing, setBrandEditing] = useState(false);
  const [brandName, setBrandName] = useState("");
  // القيمة التي حلّلها النظام تلقائيًا (قبل أي تعديل يدوي) — تُقارَن
  // بالاسم الحالي عند الخروج من وضع التعديل لمعرفة إن كان المستخدم غيّره
  // فعلًا، فيُحفظ كاسم معتمد مع الاسم السابق والنطاق كمرادفات.
  const [resolvedBrandName, setResolvedBrandName] = useState("");
  const [brandDescription, setBrandDescription] = useState("");
  const [brandAudience, setBrandAudience] = useState("");

  const [visibilityReport, setVisibilityReport] = useState<VisibilityRunDetail | null>(null);

  const [leadEmail, setLeadEmail] = useState("");
  const [leadPhone, setLeadPhone] = useState("");
  const [leadSubmitting, setLeadSubmitting] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);
  const [leadSubmitted, setLeadSubmitted] = useState(false);

  const step: Step = STEPS[stepIndex];

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem("rasid-mode");
    } catch {
      // ignore
    }
    // See the matching comment in app/page.tsx: deferred to an effect so the
    // client's first paint doesn't desync from the (localStorage-less) SSR output.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved === "dark") setDark(true);
  }, []);

  // نفس نمط الخلل اللي أصلحناه لتحليل الظهور: شاشة "brand" تنتقل إليها
  // فور اكتمال الهوية — عمدًا، حتى تبقى سريعة — لكن اكتشاف المنافسين خطوة
  // لاحقة منفصلة في نفس الـ pipeline قد لا تكون انتهت بعد عند لحظة
  // الانتقال، و suggested_competitors كانت تُؤخذ كلقطة واحدة لا تُحدَّث
  // أبدًا بعدها. هذا يعيد الجلب دوريًا لفترة محدودة بعد الوصول لشاشة
  // "brand" فقط، ويحدّث القائمة إن ظهر منافسون جدد — دون التأثير على أي
  // تعديل يدوي للاسم/الوصف (تلك حالة منفصلة).
  useEffect(() => {
    if (step !== "brand" || !storeId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const maxAttempts = 10; // كل 5 ثوانٍ تقريبًا — يغطي مدة اكتشاف المنافسين المعتادة
    const poll = async () => {
      attempts += 1;
      try {
        const fresh = await getStoreUnderstanding(storeId);
        if (disposed) return;
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setUnderstanding((prev) =>
          prev && fresh.suggested_competitors.length > prev.suggested_competitors.length ? fresh : prev
        );
        if (fresh.suggested_competitors.length === 0 && attempts < maxAttempts) {
          timer = setTimeout(poll, 5000);
        }
      } catch {
        if (!disposed && attempts < maxAttempts) timer = setTimeout(poll, 5000);
      }
    };
    poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [step, storeId]);

  const go = (n: number) => setStepIndex(Math.max(0, Math.min(STEPS.length - 1, n)));
  const next = () => go(stepIndex + 1);
  const back = () => go(stepIndex - 1);

  const startAnalysisWithUrl = async (value: string) => {
    if (!value || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const url = /^https?:\/\//i.test(value) ? value : `https://${value}`;
      const response = await createStore(url);
      setStoreId(response.store_id);
      setUnderstanding(null);
      setBrandName("");
      setBrandDescription("");
      setBrandAudience("");
      setVisibilityReport(null);
      setScanAttempt((n) => n + 1);
      go(2);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  };

  const startAnalysis = (e?: FormEvent) => {
    e?.preventDefault();
    startAnalysisWithUrl(domain.trim());
  };

  // رابط الموقع الرئيسية يمرّر النطاق عبر ?domain=... — إن وُجد، يبدأ
  // التحليل تلقائيًا بدل مطالبة المستخدم بكتابته مرة ثانية.
  useEffect(() => {
    const fromHomepage = new URLSearchParams(window.location.search).get("domain");
    if (fromHomepage && fromHomepage.trim()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDomain(fromHomepage.trim());
      startAnalysisWithUrl(fromHomepage.trim());
    }
    // مرة واحدة فقط عند التحميل الأول.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const restartAnalysis = () => {
    if (!storeId) return;
    triggerResearchRun(storeId).catch(() => {
      // A run may already be in flight (409) — the scan step's own poll
      // will reflect whatever the current run's real status is regardless.
    });
    setUnderstanding(null);
    setVisibilityReport(null);
    setScanAttempt((n) => n + 1);
    go(2);
  };

  // يبدأ تلقائيًا فور اكتمال التعرف على المتجر (لا ينتظر ضغطة المستخدم) —
  // مُطلَق في الخلفية بينما يقرأ المستخدم شاشة "brand"، ليكون التحليل قد
  // تقدّم فعلًا بحلول وصوله إلى شاشة الانتظار الثانية بدل أن يبدأ من صفر.
  //
  // خطأ حي حقيقي: مرحلة التعرف على المتجر تصل "ready" بمجرد نجاح تحديد
  // الهوية — قبل خطوة توليد الأسئلة (تعمل لاحقًا ضمن نفس عملية البحث
  // الأساسية) بخطوة كاملة. الإطلاق الفوري كان يُنشئ تحليلاً فارغًا يكتمل
  // خلال ثوانٍ بلا أي سؤال — يبدو كأن "بقية التحليل توقفت" رغم عدم وجود
  // أي خطأ. الخلفية الآن ترفض البدء (status="not_ready") حتى تتوفر أسئلة
  // فعلية، فهذه الدالة تعيد المحاولة دوريًا بدل الاكتفاء بمحاولة واحدة.
  const startVisibilityAnalysisInBackground = (id: string) => {
    let attempts = 0;
    const maxAttempts = 40; // كل 8 ثوانٍ تقريبًا — يغطي توليد الأسئلة وأي ازدحام في قائمة التنفيذ
    const attempt = () => {
      attempts += 1;
      triggerVisibilityRun(id)
        .then((res) => {
          if (res.status === "not_ready" && attempts < maxAttempts) {
            setTimeout(attempt, 8000);
          }
        })
        .catch(() => {
          // قد يكون هناك تحليل قيد التنفيذ فعلًا (409) — لا داعي لإعادة
          // المحاولة، شاشة التحليل ستعرض تقدّمه الحقيقي أيًا كان مصدر التشغيل.
        });
    };
    attempt();
  };

  const showDots = stepIndex >= 2;
  const flowIndex = Math.max(0, stepIndex - 2);
  const dotSteps = STEPS.slice(2);
  const showBackTop = stepIndex === STEPS.length - 1;

  return (
    <div
      dir="rtl"
      data-mode={dark ? "dark" : undefined}
      className="rasid-landing rl-signup-grid"
      style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: "100vh", background: "var(--ink)" }}
    >
      <div style={{ position: "relative", display: "flex", flexDirection: "column", padding: "22px 28px 34px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 13.5, color: "var(--mut)" }}>
          <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: 7, color: "inherit" }}>
            <span style={{ fontSize: 14, lineHeight: 1 }}>‹]</span>خروج
          </Link>
          <div style={{ flex: 1 }} />
          {showBackTop && (
            <button onClick={back} style={{ border: 0, background: "transparent", cursor: "pointer", color: "var(--mut)", fontSize: 13.5, fontWeight: 500 }}>
              رجوع ›
            </button>
          )}
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
                  حلّل متجرك واعرف أين يظهر، ومن يظهر بدلًا منه، وما الذي يمكنك تحسينه.
                </p>
                <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, marginTop: 26, width: "auto", padding: "12px 24px" }}>
                  حلّل متجري
                </button>
              </div>
            )}

            {step === "url" && (
              <form onSubmit={startAnalysis}>
                <h1 style={{ margin: 0, fontSize: 27, fontWeight: 600, letterSpacing: "-.02em" }}>أدخل رابط متجرك</h1>
                <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.8 }}>
                  سنقرأ منتجاتك ونقارن ظهورك بالمتاجر التي تنافسك.
                </p>
                <div style={{ marginTop: 26, fontSize: 13, fontWeight: 600 }}>رابط الموقع</div>
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <div
                    dir="ltr"
                    style={{
                      flex: 1,
                      minWidth: 220,
                      display: "flex",
                      alignItems: "center",
                      border: "1px solid var(--line)",
                      borderRadius: 11,
                      background: "var(--panel)",
                      overflow: "hidden",
                    }}
                  >
                    <span
                      className="mono"
                      style={{
                        fontSize: 12.5,
                        color: "var(--dim)",
                        padding: "0 12px",
                        borderRight: "1px solid var(--line)",
                        alignSelf: "stretch",
                        display: "flex",
                        alignItems: "center",
                        background: "var(--panel2)",
                      }}
                    >
                      https://
                    </span>
                    <input
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="example.com"
                      dir="ltr"
                      style={{ flex: 1, minWidth: 0, background: "transparent", border: 0, outline: "none", color: "var(--tx)", fontSize: 14, padding: 12, textAlign: "left" }}
                    />
                  </div>
                  <button type="submit" disabled={creating || !domain.trim()} className="rl-fill-soft" style={{ ...solidBtn, padding: "12px 20px", whiteSpace: "nowrap", opacity: creating || !domain.trim() ? 0.5 : 1 }}>
                    {creating ? "جارٍ البدء…" : "ابدأ التحليل"}
                  </button>
                </div>
                {createError && <p style={{ marginTop: 12, fontSize: 12.5, color: "#e0685f" }}>{createError}</p>}
              </form>
            )}

            {step === "scan" && storeId && (
              <ScanStep
                key={`${storeId}-${scanAttempt}`}
                storeId={storeId}
                domain={domain || understanding?.url || ""}
                onReady={(u) => {
                  setUnderstanding(u);
                  setBrandName(u.display_name ?? "");
                  setResolvedBrandName(u.display_name ?? "");
                  setBrandDescription(u.description ?? "");
                  setBrandAudience(u.target_audience.join("، "));
                  startVisibilityAnalysisInBackground(storeId);
                  next();
                }}
              />
            )}

            {step === "brand" && (
              <div>
                <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>هذا ما فهمناه عن متجرك</h1>
                <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
                  تأكد من المعلومات حتى تكون النتائج مناسبة لنشاطك.
                </p>

                {!brandEditing ? (
                  <div style={{ marginTop: 22, border: "1px solid var(--line)", borderRadius: 14, background: "var(--panel)", overflow: "hidden" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
                      <tbody>
                        <BrandTableRow label="اسم المتجر" bold>
                          {brandName.trim() || domain.trim() || understanding?.url || "متجرك"}
                        </BrandTableRow>
                        {understanding?.business_type && (
                          <BrandTableRow label="نوع النشاط">{understanding.business_type}</BrandTableRow>
                        )}
                        {(understanding?.country || understanding?.city) && (
                          <BrandTableRow label="السوق">
                            {[understanding?.city, understanding?.country].filter(Boolean).join("، ")}
                          </BrandTableRow>
                        )}
                        <BrandTableRow label="المنتجات المكتشفة" mono>
                          {arDigits(understanding?.products_found ?? 0)}
                        </BrandTableRow>
                        <BrandTableRow label="الفئات المكتشفة" mono>
                          {arDigits(understanding?.categories_found ?? 0)}
                        </BrandTableRow>
                        {(() => {
                          const chips = understanding?.top_categories.length
                            ? understanding.top_categories.map((c) => c.name)
                            : (understanding?.product_samples ?? []).slice(0, 6).map((p) => p.name);
                          return chips.length > 0 ? (
                            <BrandTableRow label="أهم التصنيفات">
                              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                                {chips.slice(0, 6).map((label) => (
                                  <span key={label} style={{ fontSize: 11, color: "var(--mut)", border: "1px solid var(--line)", borderRadius: 9999, padding: "3px 10px" }}>
                                    {label}
                                  </span>
                                ))}
                              </div>
                            </BrandTableRow>
                          ) : null;
                        })()}
                        <BrandTableRow label="ماذا يبيع المتجر">
                          <span style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", lineHeight: 1.7 }}>
                            {brandDescription || "لم نستطع تحديد ماذا يبيع متجرك بوضوح بعد."}
                          </span>
                        </BrandTableRow>
                        <BrandTableRow label="من هم عملاؤه؟" last>
                          {brandAudience || "لا توجد بيانات كافية لمعرفة عملاء متجرك بعد."}
                        </BrandTableRow>
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ marginTop: 22 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>اسم المتجر</div>
                    <input value={brandName} onChange={(e) => setBrandName(e.target.value)} style={textInput} />
                    <div style={fieldLabel}>ماذا يبيع المتجر؟</div>
                    <textarea
                      rows={4}
                      value={brandDescription}
                      onChange={(e) => setBrandDescription(e.target.value)}
                      style={{ ...textInput, fontSize: 13, lineHeight: 1.9, resize: "vertical" }}
                    />
                    <div style={fieldLabel}>من هم عملاؤه؟</div>
                    <input value={brandAudience} onChange={(e) => setBrandAudience(e.target.value)} style={{ ...textInput, fontSize: 13.5 }} />
                  </div>
                )}

                {understanding && (
                  <p style={captionNote}>
                    استنادًا إلى {arDigits(understanding.pages_crawled)} صفحة و{arDigits(understanding.products_found)} منتج و
                    {arDigits(understanding.categories_found)} فئة رصدناها فعليًا من متجرك.
                  </p>
                )}

                {understanding && understanding.suggested_competitors.length > 0 && storeId && (
                  <SuggestedCompetitorsPanel
                    storeId={storeId}
                    competitors={understanding.suggested_competitors}
                    onUpdate={(updated) =>
                      setUnderstanding((prev) =>
                        prev
                          ? {
                              ...prev,
                              suggested_competitors: prev.suggested_competitors.map((c) =>
                                c.id === updated.id ? updated : c
                              ),
                            }
                          : prev
                      )
                    }
                  />
                )}

                <div style={stepNavRow}>
                  <button
                    onClick={() => {
                      if (brandEditing) {
                        const edited = brandName.trim();
                        if (storeId && edited && edited !== resolvedBrandName.trim()) {
                          // احفظه كاسم معتمد؛ الاسم السابق ونطاق المتجر يصبحان
                          // مرادفَين تلقائيًا (انظر confirmStoreBrandName في الخلفية)
                          // — لا يوقف هذا تحليل الظهور ولا ينتظره، فهو يعمل أصلًا.
                          confirmStoreBrandName(storeId, edited)
                            .then(() => setResolvedBrandName(edited))
                            .catch(() => {
                              // غير حرج — الاسم يبقى معروضًا محليًا حتى لو تعذّر الحفظ.
                            });
                        }
                      }
                      setBrandEditing((v) => !v);
                    }}
                    style={backLink}
                  >
                    {brandEditing ? "تم" : "تعديل"}
                  </button>
                  <div style={{ flex: 1 }} />
                  <button onClick={next} className="rl-fill-soft" style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}>
                    المعلومات صحيحة
                  </button>
                </div>
                <button onClick={restartAnalysis} style={{ ...secondaryLink, border: 0, background: "transparent", cursor: "pointer" }}>
                  ↻ لا يبدو هذا صحيحًا — أعد التحليل
                </button>
              </div>
            )}

            {step === "analyzing" && storeId && (
              <AnalyzingStep storeId={storeId} report={visibilityReport} setReport={setVisibilityReport} onComplete={next} />
            )}

            {step === "result" && <ResultStep report={visibilityReport} onNext={next} onBack={back} />}

            {step === "competitors" && (
              <VisibilityCompetitorsStep report={visibilityReport} onNext={next} onBack={back} />
            )}

            {step === "search" && (
              <SearchResultsStep report={visibilityReport} onNext={next} onBack={back} />
            )}

            {step === "citations" && (
              <CitationsStep report={visibilityReport} onNext={next} onBack={back} />
            )}

            {step === "recommendations" && (
              <VisibilityRecommendationsStep report={visibilityReport} onNext={next} onBack={back} />
            )}

            {step === "join" && (
              <div>
                <h1 style={{ margin: 0, fontSize: "clamp(24px,2.8vw,30px)", fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1.35 }}>
                  هل تريد تقريرًا كاملًا عن ظهور علامتك؟
                </h1>
                <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.85 }}>
                  انضم إلى النسخة التجريبية للحصول على تحليل أعمق ومتابعة ظهور علامتك.
                </p>
                <div style={{ marginTop: 22, fontSize: 13, fontWeight: 600 }}>البريد الإلكتروني</div>
                <input value={leadEmail} onChange={(e) => setLeadEmail(e.target.value)} dir="ltr" style={{ ...textInput, textAlign: "left" }} />
                <div style={fieldLabel}>رقم الجوال (اختياري)</div>
                <input value={leadPhone} onChange={(e) => setLeadPhone(e.target.value)} dir="ltr" style={{ ...textInput, textAlign: "left" }} />
                <button
                  onClick={async () => {
                    if (!storeId || !leadEmail.trim() || leadSubmitting) return;
                    setLeadSubmitting(true);
                    setLeadError(null);
                    try {
                      const email = leadEmail.trim();
                      const phone = leadPhone.trim();
                      await createOnboardingLead(storeId, email, phone ? `${email} — ${phone}` : email);
                      setLeadSubmitted(true);
                    } catch (err) {
                      setLeadError(err instanceof Error ? err.message : String(err));
                    } finally {
                      setLeadSubmitting(false);
                    }
                  }}
                  disabled={leadSubmitting || !leadEmail.trim()}
                  className="rl-fill-soft"
                  style={{ ...solidBtn, marginTop: 18, width: "100%", opacity: leadSubmitting || !leadEmail.trim() ? 0.5 : 1 }}
                >
                  {leadSubmitting ? "جارٍ الإرسال…" : "انضم إلى النسخة التجريبية"}
                </button>
                <p style={captionNote}>المقاعد محدودة خلال مرحلة التجربة.</p>
                {leadError && <p style={{ marginTop: 8, fontSize: 12.5, color: "#e0685f" }}>{leadError}</p>}
                {leadSubmitted && (
                  <div style={{ marginTop: 14, fontSize: 12.5, color: "var(--acc)", textAlign: "center" }}>
                    وصلنا طلبك، وسنتواصل معك لتفعيل تجربتك.
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
            ظهور يرصد الأسئلة التي يطرحها عملاؤك على الذكاء الاصطناعي — ويخبرك من يُوصى به.
          </div>
        </div>
      </div>
    </div>
  );
}

function BrandTableRow({
  label,
  children,
  bold,
  mono,
  last,
}: {
  label: string;
  children: ReactNode;
  bold?: boolean;
  mono?: boolean;
  last?: boolean;
}) {
  return (
    <tr style={{ borderBottom: last ? "none" : "1px solid var(--line)" }}>
      <td style={{ padding: "12px 14px", fontSize: 12, color: "var(--dim)", whiteSpace: "nowrap", verticalAlign: "top", width: "36%" }}>{label}</td>
      <td className={mono ? "mono" : undefined} style={{ padding: "12px 14px", fontWeight: bold ? 600 : 400, verticalAlign: "top" }}>{children}</td>
    </tr>
  );
}

/** Flavor sub-messages shown while a phase is active, purely to keep the
 * step visibly moving — never a claim about a specific data point, so it
 * carries no fabrication risk. Cycles on a timer independent of polling. */
const SCAN_SUBTEXT: Record<number, string[]> = {
  0: ["نبحث عن متجرك على الويب", "نحدد اسم علامتك التجارية", "نتعرف على نشاطك التجاري"],
  1: ["نحدد نوع نشاطك", "نستخرج الفئات والمنتجات", "نلخّص ما يبيعه متجرك"],
  2: ["نبحث عن منافسيك", "نجهّز مقارنة المنافسين", "سيبدأ بعد اكتمال الفهم"],
};

// Stages where identity resolution is still in flight — keep polling, same
// UX either way (the legacy "pending" pre-identity-decoupling case and the
// new "resolving_identity" case both just mean "still working").
const POLLING_STAGES = new Set(["pending", "resolving_identity"]);
// Stages that mean registration can proceed right now — the whole point of
// decoupling identity from the catalog crawl is that none of these ever
// wait on catalog_scanning/catalog_blocked to finish.
const READY_TO_ADVANCE_STAGES = new Set(["ready", "provisional", "catalog_scanning", "catalog_blocked"]);

function ScanStep({ storeId, domain, onReady }: { storeId: string; domain: string; onReady: (u: StoreUnderstanding) => void }) {
  const [failed, setFailed] = useState(false);
  // "low_confidence" (legacy) means the crawl finished but found too little
  // to trust. "needs_confirmation" (new) means identity resolution found a
  // plausible brand but below the confidence bar. Both surface a message —
  // but needs_confirmation is never a hard wall, only low_confidence is.
  const [lowConfidence, setLowConfidence] = useState(false);
  const [needsConfirmation, setNeedsConfirmation] = useState<StoreUnderstanding | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [live, setLive] = useState<StoreUnderstanding | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getStoreUnderstanding(storeId);
        if (disposed) return;
        setPollError(null);
        setLive(result);
        if (POLLING_STAGES.has(result.understanding_stage)) {
          timer = setTimeout(poll, 2000);
        } else if (result.understanding_stage === "failed") {
          setFailed(true);
        } else if (result.understanding_stage === "low_confidence") {
          setLowConfidence(true);
        } else if (result.understanding_stage === "needs_confirmation") {
          setNeedsConfirmation(result);
        } else if (READY_TO_ADVANCE_STAGES.has(result.understanding_stage)) {
          onReady(result);
        } else {
          // Unrecognized future stage value — keep polling rather than
          // silently advancing on data we don't know how to interpret yet.
          timer = setTimeout(poll, 2000);
        }
      } catch (err) {
        if (!disposed) {
          setPollError(err instanceof Error ? err.message : String(err));
          timer = setTimeout(poll, 3000);
        }
      }
    };
    poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
    // onReady is a fresh closure each render (it captures next()); only the
    // storeId identifies this scan attempt, so it alone should drive re-polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  // Keeps the active phase's sub-message rotating so the step never looks
  // stuck, independent of how often the real poll above actually resolves.
  useEffect(() => {
    if (failed || lowConfidence || needsConfirmation) return;
    const timer = setInterval(() => setTick((t) => t + 1), 1900);
    return () => clearInterval(timer);
  }, [failed, lowConfidence, needsConfirmation]);

  const hasPages = !!live && live.pages_crawled > 0;
  // Identity resolved via web search is just as valid a "we know your
  // store" signal as having read pages — often the only one available on a
  // blocked/bot-protected site (the actual point of Phase 1's decoupling).
  const hasIdentity = !!live && (live.identity_confidence !== null || hasPages);
  const hasProducts = !!live && live.products_found > 0;
  const catalogSettled = !!live && ["ready", "partial", "blocked", "failed"].includes(live.catalog_status);
  const stageDone = !!live && !POLLING_STAGES.has(live.understanding_stage);

  const phases: { label: string; done: boolean; active: boolean; detail: string | null }[] = [
    {
      label: "نتعرف على متجرك",
      done: hasIdentity,
      active: !hasIdentity,
      detail: live && live.pages_crawled > 0 ? `قرأنا ${arDigits(live.pages_crawled)} صفحة حتى الآن` : null,
    },
    {
      label: "نتعرف على منتجاتك وفئاتك",
      done: hasProducts || catalogSettled,
      active: hasIdentity && !(hasProducts || catalogSettled),
      detail: hasProducts ? `اكتشفنا ${arDigits(live!.products_found)} منتجًا ضمن ${arDigits(live!.categories_found)} فئة` : null,
    },
    {
      label: "نلخّص نشاطك ونجهّز التحليل",
      done: stageDone,
      active: (hasProducts || catalogSettled) && !stageDone,
      detail: null,
    },
  ];

  const doneCount = phases.filter((p) => p.done).length;

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 27, fontWeight: 600, letterSpacing: "-.02em" }}>نحلل ظهور متجرك</h1>
      <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--mut)", lineHeight: 1.8 }}>
        نبحث عن متجرك بالطريقة التي يبحث بها عملاؤك.
      </p>

      <div style={{ marginTop: 22, height: 3, borderRadius: 9999, background: "var(--line)", overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${(doneCount / phases.length) * 100}%`,
            background: "var(--acc)",
            transition: "width .5s ease",
          }}
        />
      </div>

      <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 15 }}>
        {phases.map((p, i) => {
          const subtexts = SCAN_SUBTEXT[i] ?? [];
          const activeSubtext = p.active && subtexts.length > 0 ? subtexts[tick % subtexts.length] : null;
          return (
            <div key={p.label} style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>
              <span
                style={{
                  width: 16,
                  height: 16,
                  marginTop: 1,
                  flex: "none",
                  borderRadius: "50%",
                  border: `1.5px solid ${p.done ? "var(--acc)" : p.active ? "var(--acc)" : "var(--line)"}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 9,
                  color: "var(--acc)",
                  animation: p.active && !p.done ? "ospin 1.6s linear infinite" : "none",
                }}
              >
                {p.done ? "✓" : ""}
              </span>
              <div>
                <div style={{ fontSize: 13.5, color: p.done || p.active ? "var(--tx)" : "var(--dim)", fontWeight: p.active ? 600 : 400 }}>
                  {p.label}
                </div>
                {(p.detail || activeSubtext) && (
                  <div key={p.detail ?? activeSubtext} style={{ marginTop: 3, fontSize: 12, color: p.done ? "var(--acc)" : "var(--dim)", animation: "rrise .35s ease both" }}>
                    {p.detail ?? activeSubtext}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {failed && (
        <div style={{ marginTop: 20 }}>
          <p style={{ fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
            تعذّر الوصول إلى متجرك — قد يكون الموقع غير متاح مؤقتًا أو يمنع القراءة الآلية.
          </p>
          <button
            onClick={() => {
              triggerResearchRun(storeId).catch(() => {});
              setFailed(false);
            }}
            className="rl-ghost-line"
            style={{ ...nextBtn, marginTop: 10 }}
          >
            حاول مجددًا
          </button>
        </div>
      )}
      {lowConfidence && (
        <div style={{ marginTop: 20 }}>
          <p style={{ fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
            لم نتمكن من قراءة متجرك بشكل كافٍ لتحديد نشاطك بثقة — قد يمنع الموقع القراءة الآلية.
          </p>
          <button
            onClick={() => {
              triggerResearchRun(storeId).catch(() => {});
              setLowConfidence(false);
            }}
            className="rl-ghost-line"
            style={{ ...nextBtn, marginTop: 10 }}
          >
            حاول مجددًا
          </button>
        </div>
      )}
      {needsConfirmation && (
        <div style={{ marginTop: 20 }}>
          <p style={{ fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
            {needsConfirmation.display_name
              ? `وجدنا اسمًا محتملًا لمتجرك: "${needsConfirmation.display_name}" — لكن لسنا متأكدين تمامًا. يمكنك المتابعة وتأكيد التفاصيل لاحقًا.`
              : "لم نتمكن من تأكيد هوية متجرك بثقة كافية بعد — يمكنك المتابعة وتأكيد التفاصيل لاحقًا."}
          </p>
          <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
            <button
              onClick={() => onReady(needsConfirmation)}
              className="rl-fill-soft"
              style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}
            >
              متابعة رغم ذلك
            </button>
            <button
              onClick={() => {
                triggerResearchRun(storeId).catch(() => {});
                setNeedsConfirmation(null);
              }}
              className="rl-ghost-line"
              style={nextBtn}
            >
              حاول مجددًا
            </button>
          </div>
        </div>
      )}
      {pollError && <p style={{ marginTop: 8, fontSize: 12, color: "var(--dim)" }}>تعذّر الاتصال مؤقتًا، نعيد المحاولة تلقائيًا…</p>}
      {domain && !failed && !lowConfidence && !needsConfirmation && <p style={captionNote}>نحلل {domain} الآن ببيانات حقيقية من متجرك.</p>}
    </div>
  );
}

function visibilityStrengthLabel(appearanceRate: number | null): string {
  if (appearanceRate === null) return "";
  if (appearanceRate >= 0.4) return "ظهور قوي";
  if (appearanceRate >= 0.15) return "ظهور متوسط";
  return "ظهور ضعيف";
}

function useVisibilityReportPoll(
  storeId: string | null,
  setReport: Dispatch<SetStateAction<VisibilityRunDetail | null>>,
  maxAttempts: number,
) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storeId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      try {
        const data = await getLatestVisibilityRun(storeId);
        if (disposed) return;
        setReport(data);
        setError(null);
        setLoading(false);
        // أكثر من 160 عملية بحث حقيقية تأخذ دقائق — نستمر بالسؤال دوريًا
        // دون حجب بقية رحلة التسجيل.
        if ((data.status === "no_run_yet" || data.status === "running") && attempts < maxAttempts) {
          timer = setTimeout(poll, 8000);
        }
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
          if (attempts < maxAttempts) timer = setTimeout(poll, 8000);
        }
      }
    };
    poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  return { loading, error };
}

// المرحلة الثانية الموحّدة — "تحليل ظهور علامتك" شاشة تقدّم واحدة فقط، بلا
// مراحل فرعية ظاهرة (اكتشاف منافسين/جمع مصادر/تحليل إجابات تبقى عمليات
// داخلية). تنتقل تلقائيًا إلى شاشات التقرير فور الاكتمال.
function AnalyzingStep({
  storeId,
  report,
  setReport,
  onComplete,
}: {
  storeId: string;
  report: VisibilityRunDetail | null;
  setReport: Dispatch<SetStateAction<VisibilityRunDetail | null>>;
  onComplete: () => void;
}) {
  const { error } = useVisibilityReportPoll(storeId, setReport, 90);
  const status = report?.status;

  useEffect(() => {
    if (status === "completed") onComplete();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const completed = report?.completed_count ?? 0;
  const total = report?.total_planned || 90;
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>
        {status === "completed" ? "اكتمل تحليل ظهور علامتك" : "نحلل ظهور علامتك"}
      </h1>
      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
        نراجع عمليات البحث المرتبطة بمنتجاتك وسوقك لمعرفة متى تظهر علامتك، وما مركزها، ومن يظهر قبلها.
      </p>

      <div style={{ marginTop: 26, height: 4, borderRadius: 9999, background: "var(--line)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${percent}%`, background: "var(--acc)", transition: "width .6s ease" }} />
      </div>

      <p className="mono" style={{ marginTop: 16, fontSize: 14, fontWeight: 700, textAlign: "center", color: "var(--tx)" }}>
        تم تحليل {arDigits(completed)} من {arDigits(total)}
      </p>

      {error && (
        <p style={{ marginTop: 10, fontSize: 12, color: "var(--dim)", textAlign: "center" }}>
          تعذّر التحديث مؤقتًا، نعيد المحاولة تلقائيًا…
        </p>
      )}
    </div>
  );
}

function ResultStep({
  report,
  onNext,
  onBack,
}: {
  report: VisibilityRunDetail | null;
  onNext: () => void;
  onBack: () => void;
}) {
  const stat: CSSProperties = { border: "1px solid var(--line)", borderRadius: 14, background: "var(--panel)", padding: "16px 14px", textAlign: "center" };

  const data = report?.report;
  const isReady = report?.status === "completed" && !!data && data.total_searches > 0;

  if (!isReady) {
    return (
      <div>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>ظهور علامتك</h1>
        <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
          لم يكتمل تحليل ظهور علامتك بعد.
        </p>
        <div style={stepNavRow}>
          <button onClick={onBack} style={backLink}>‹ رجوع</button>
        </div>
      </div>
    );
  }

  const appearancePercent = data.appearance_rate !== null ? Math.round(data.appearance_rate * 100) : null;
  const avgRankText = data.avg_rank !== null ? arDigits(Math.round(data.avg_rank * 10) / 10) : "—";

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>ظهور علامتك</h1>
      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
        حللنا أكثر من {arDigits(data.total_searches)} عملية بحث مرتبطة بمنتجاتك وسوقك لمعرفة متى تظهر علامتك، وما ترتيبها، ومن يظهر قبلها.
      </p>

      <p style={{ margin: "18px 0 0", fontSize: 15, fontWeight: 700, lineHeight: 1.7, color: "var(--tx)" }}>
        ظهرت علامتك في {arDigits(data.mentioned_count)} من {arDigits(data.total_searches)} عملية بحث
      </p>
      <p style={{ margin: "6px 0 0", fontSize: 13, fontWeight: 600, color: "var(--acc)" }}>
        {visibilityStrengthLabel(data.appearance_rate)}
      </p>

      <div style={{ marginTop: 18, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
        <div style={stat}>
          <div style={{ fontSize: 11, color: "var(--dim)" }}>نسبة الظهور</div>
          <div className="mono" style={{ marginTop: 6, fontSize: 15, fontWeight: 700 }}>
            {appearancePercent !== null ? `${arDigits(appearancePercent)}%` : "—"}
          </div>
        </div>
        <div style={stat}>
          <div style={{ fontSize: 11, color: "var(--dim)" }}>متوسط مركزها عند الظهور</div>
          <div className="mono" style={{ marginTop: 6, fontSize: 15, fontWeight: 700 }}>{avgRankText}</div>
        </div>
        <div style={stat}>
          <div style={{ fontSize: 11, color: "var(--dim)" }}>ضمن أفضل ٣ نتائج</div>
          <div className="mono" style={{ marginTop: 6, fontSize: 15, fontWeight: 700 }}>
            {arDigits(data.top3_count)} {data.top3_count === 1 ? "مرة" : "مرات"}
          </div>
        </div>
      </div>

      <p style={{ marginTop: 16, fontSize: 13.5, lineHeight: 1.9, color: "var(--tx)" }}>
        {data.competitors_ahead_count > 0
          ? `${arDigits(data.competitors_ahead_count)} ${data.competitors_ahead_count === 1 ? "منافس ظهر" : "منافسين ظهروا"} قبل علامتك في نفس عمليات البحث.`
          : "لم يظهر أي منافس قبل علامتك بثبات في عمليات البحث التي قِسناها."}
      </p>

      <div style={stepNavRow}>
        <button onClick={onBack} style={backLink}>‹ رجوع</button>
        <div style={{ flex: 1 }} />
        <button onClick={onNext} className="rl-fill-soft" style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}>
          اعرف من يظهر قبلك
        </button>
      </div>
    </div>
  );
}

function CompetitorLogo({ domain, name }: { domain: string; name: string }) {
  return (
    <span
      style={{
        position: "relative",
        width: 24,
        height: 24,
        flex: "none",
        borderRadius: 7,
        overflow: "hidden",
        background: "var(--panel2)",
        border: "1px solid var(--line)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 10.5,
        fontWeight: 700,
        color: "var(--mut)",
      }}
    >
      {name.trim().charAt(0) || "؟"}
      {/* eslint-disable-next-line @next/next/no-img-element -- a small real
          favicon fetched from the competitor's own domain, not our asset pipeline */}
      <img
        src={`https://www.google.com/s2/favicons?sz=64&domain=${encodeURIComponent(domain)}`}
        alt=""
        width={24}
        height={24}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        onError={(e) => {
          e.currentTarget.style.display = "none";
        }}
      />
    </span>
  );
}

// Phase 6 — surfaces Phase 4's identity-based competitor suggestions
// (found via web search, independent of SERP/AI-visibility measurement)
// right on the brand-confirmation step, with inline confirm/reject so a
// human decision is never a hard requirement to keep going.
const SUGGESTED_COMPETITORS_DEFAULT_LIMIT = 4;

function SuggestedCompetitorsPanel({
  storeId,
  competitors,
  onUpdate,
}: {
  storeId: string;
  competitors: SuggestedCompetitorItem[];
  onUpdate: (updated: SuggestedCompetitorItem) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = competitors.filter((c) => c.confirmation_status !== "user_rejected");
  if (visible.length === 0) return null;

  const shown = expanded ? visible : visible.slice(0, SUGGESTED_COMPETITORS_DEFAULT_LIMIT);
  const remaining = visible.length - shown.length;

  const act = async (competitorId: string, action: "confirm" | "reject") => {
    try {
      const updated = await postCompetitorConfirmation(storeId, competitorId, action);
      onUpdate(updated);
    } catch {
      // Non-critical — the suggestion just stays as-is; the user can retry.
    }
  };

  return (
    <div style={{ marginTop: 22 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>منافسون اكتشفناهم لك</div>
      <div style={{ border: "1px solid var(--line)", borderRadius: 14, background: "var(--panel)", overflow: "hidden" }}>
        {shown.map((c, i) => {
          const isConfirmed = c.confirmation_status === "auto_confirmed" || c.confirmation_status === "user_confirmed";
          return (
            <div
              key={c.id}
              style={{
                display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                borderBottom: i === shown.length - 1 && !remaining ? "none" : "1px solid var(--line)",
              }}
            >
              <CompetitorLogo domain={c.domain} name={c.name} />
              <div style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {c.name}
              </div>
              {isConfirmed ? (
                <button onClick={() => act(c.id, "reject")} style={{ ...backLink, fontSize: 12, whiteSpace: "nowrap" }}>
                  إزالة
                </button>
              ) : (
                <div style={{ display: "flex", gap: 6, flex: "none" }}>
                  <button
                    onClick={() => act(c.id, "confirm")}
                    className="rl-ghost-line"
                    style={{ ...nextBtn, padding: "6px 12px", fontSize: 12 }}
                  >
                    تأكيد
                  </button>
                  <button onClick={() => act(c.id, "reject")} style={{ ...backLink, fontSize: 12, whiteSpace: "nowrap" }}>
                    ليس منافسًا
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {remaining > 0 && (
          <button
            onClick={() => setExpanded(true)}
            style={{
              width: "100%", textAlign: "center", border: 0, background: "var(--panel2)", cursor: "pointer",
              color: "var(--mut)", fontSize: 12.5, padding: "9px 12px",
            }}
          >
            عرض {arDigits(remaining)} {remaining === 1 ? "آخر" : "آخرين"}
          </button>
        )}
      </div>
    </div>
  );
}

function VisibilityCompetitorsStep({
  report,
  onNext,
  onBack,
}: {
  report: VisibilityRunDetail | null;
  onNext: () => void;
  onBack: () => void;
}) {
  const competitors = report?.report?.top_competitors ?? [];
  const clientRate = report?.report?.appearance_rate ?? null;
  const clientRank = report?.report?.client_rank ?? null;
  const totalConsidered = report?.report?.competitors_considered_count ?? 0;

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>هذه المتاجر تظهر أمام عملائك</h1>
      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
        قارن نسبة ظهور متجرك بأبرز المتاجر المنافسة في نفس عمليات البحث.
      </p>
      {clientRank !== null && totalConsidered > 0 && (
        <p style={{ margin: "10px 0 0", fontSize: 13, fontWeight: 600, color: "var(--tx)" }}>
          ترتيب ظهور علامتك بين أبرز المنافسين: {arDigits(clientRank)} من {arDigits(totalConsidered)}
        </p>
      )}

      {competitors.length === 0 ? (
        <p style={{ marginTop: 20, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
          لم نكتشف متاجر منافسة ظاهرة بثبات في عمليات البحث التي قِسناها بعد.
        </p>
      ) : (
        <div style={{ marginTop: 20, border: "1px solid var(--line)", borderRadius: 14, background: "var(--panel)", overflow: "hidden" }}>
          <div style={{ display: "flex", padding: "10px 14px", fontSize: 11, color: "var(--dim)", borderBottom: "1px solid var(--line)" }}>
            <span style={{ flex: 1 }}>المتجر</span>
            <span>نسبة الظهور</span>
          </div>
          {competitors.map((c) => {
            const diffPoints = clientRate !== null ? Math.round((c.appearance_rate - clientRate) * 100) : null;
            return (
              <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", borderBottom: "1px solid var(--line)", fontSize: 13.5 }}>
                <CompetitorLogo domain={c.domain ?? ""} name={c.name} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</div>
                  <div style={{ marginTop: 2, fontSize: 11, color: "var(--dim)" }}>
                    ظهر {arDigits(c.appearances)} {c.appearances === 1 ? "مرة" : "مرات"}
                    {c.avg_rank !== null && ` — بمتوسط مركز ${arDigits(Math.round(c.avg_rank * 10) / 10)}`}
                    {diffPoints !== null && diffPoints !== 0 && (
                      <> — {diffPoints > 0 ? `أعلى منك بـ ${arDigits(diffPoints)} نقطة` : `أقل منك بـ ${arDigits(Math.abs(diffPoints))} نقطة`}</>
                    )}
                  </div>
                </div>
                <span className="mono" style={{ color: "var(--mut)", whiteSpace: "nowrap" }}>{arDigits(Math.round(c.appearance_rate * 100))}%</span>
              </div>
            );
          })}
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "rgba(14,157,134,.08)", fontSize: 13.5, fontWeight: 600 }}>
            <span style={{ width: 24, flex: "none", textAlign: "center" }}>—</span>
            <span style={{ flex: 1 }}>متجرك</span>
            <span className="mono">{clientRate !== null ? `${arDigits(Math.round(clientRate * 100))}%` : "—"}</span>
          </div>
        </div>
      )}

      <div style={stepNavRow}>
        <button onClick={onBack} style={backLink}>‹ رجوع</button>
        <div style={{ flex: 1 }} />
        <button onClick={onNext} className="rl-fill-soft" style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}>
          اطّلع على عمليات البحث
        </button>
      </div>
    </div>
  );
}

const SEARCH_CATEGORY_LABELS: Record<string, string> = {
  recommendation: "توصية", best: "الأفضل", comparison: "مقارنة", alternatives: "بدائل",
  product_discovery: "اكتشاف منتج", local: "محلي", problem_solution: "حل مشكلة",
  occasion: "مناسبة", price: "سعر",
};

function pickBestAnswer(question: VisibilityRunDetail["questions"][number]) {
  const successful = question.answers.filter((a) => a.status === "success");
  return successful.find((a) => a.brand_mentioned) ?? successful[0] ?? question.answers[0] ?? null;
}

function SearchResultsStep({
  report,
  onNext,
  onBack,
}: {
  report: VisibilityRunDetail | null;
  onNext: () => void;
  onBack: () => void;
}) {
  const questions = report?.questions ?? [];
  // عيّنة تمثيلية من الأسئلة الحقيقية — أولوية للأسئلة التي ظهرت فيها
  // العلامة، بدل عرض 160+ سطرًا دفعة واحدة.
  const withAnswers = questions.filter((q) => q.answers.length > 0);
  const mentioned = withAnswers.filter((q) => pickBestAnswer(q)?.brand_mentioned);
  const notMentioned = withAnswers.filter((q) => !pickBestAnswer(q)?.brand_mentioned);
  const sample = [...mentioned.slice(0, 6), ...notMentioned.slice(0, 6)].slice(0, 10);

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>عيّنة من عمليات البحث</h1>
      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
        هذا مثال من عمليات البحث الحقيقية التي قِسنا فيها ظهور علامتك.
      </p>

      {sample.length === 0 ? (
        <p style={{ marginTop: 20, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
          لا تزال نتائج عمليات البحث قيد الإعداد.
        </p>
      ) : (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 10, maxHeight: 340, overflowY: "auto" }}>
          {sample.map((q) => {
            const answer = pickBestAnswer(q);
            const source = answer?.sources?.[0] ?? null;
            return (
              <div key={q.question_id} style={{ border: "1px solid var(--line)", borderRadius: 12, background: "var(--panel)", padding: "12px 14px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 11, color: "var(--dim)", border: "1px solid var(--line)", borderRadius: 9999, padding: "2px 8px" }}>
                    {SEARCH_CATEGORY_LABELS[q.category] ?? q.category}
                  </span>
                  <span
                    style={{
                      marginRight: "auto", fontSize: 11.5, fontWeight: 600,
                      color: answer?.brand_mentioned ? "var(--acc)" : "var(--dim)",
                    }}
                  >
                    {answer?.brand_mentioned
                      ? `ظهرت${answer.mention_rank ? ` — المركز ${arDigits(answer.mention_rank)}` : ""}`
                      : "لم تظهر"}
                  </span>
                </div>
                <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--tx)", lineHeight: 1.7 }}>{q.text}</p>
                {answer?.brand_mentioned && (
                  <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--dim)" }}>
                    {answer.mention_type === "recommended" ? "توصية فعلية" : "مجرد ذكر"}
                  </p>
                )}
                {source && (
                  <p style={{ margin: "6px 0 0", fontSize: 11, color: "var(--dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    المصدر: {source.title || source.url}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div style={stepNavRow}>
        <button onClick={onBack} style={backLink}>‹ رجوع</button>
        <div style={{ flex: 1 }} />
        <button onClick={onNext} className="rl-fill-soft" style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}>
          اطّلع على المصادر
        </button>
      </div>
    </div>
  );
}

const CITATION_SUPPORTS_LABEL: Record<string, string> = {
  client: "دعم ظهورك",
  competitor: "دعم منافسًا",
  mixed: "دعم الطرفين",
};

function CitationsStep({
  report,
  onNext,
  onBack,
}: {
  report: VisibilityRunDetail | null;
  onNext: () => void;
  onBack: () => void;
}) {
  const citations = report?.report?.citations ?? [];

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>أبرز المصادر</h1>
      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
        هذه المواقع تكررت في نتائج عمليات البحث التي قِسنا فيها ظهور علامتك.
      </p>

      {citations.length === 0 ? (
        <p style={{ marginTop: 20, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
          لم نجد مصادر خارجية تكررت بثبات في عمليات البحث التي قِسناها بعد.
        </p>
      ) : (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 8 }}>
          {citations.map((c) => (
            <div
              key={c.domain}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                border: "1px solid var(--line)", borderRadius: 12, padding: "10px 14px", fontSize: 13.5,
              }}
            >
              <CompetitorLogo domain={c.domain} name={c.domain} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div dir="ltr" style={{ textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.domain}
                </div>
                <div style={{ marginTop: 2, fontSize: 11, color: "var(--dim)" }}>{CITATION_SUPPORTS_LABEL[c.supports] ?? c.supports}</div>
              </div>
              <span className="mono" style={{ color: "var(--mut)", whiteSpace: "nowrap" }}>
                {arDigits(c.citation_count)} {c.citation_count === 1 ? "استشهاد" : "استشهادات"}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={stepNavRow}>
        <button onClick={onBack} style={backLink}>‹ رجوع</button>
        <div style={{ flex: 1 }} />
        <button onClick={onNext} className="rl-fill-soft" style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}>
          شاهد التوصيات
        </button>
      </div>
    </div>
  );
}

function VisibilityRecommendationsStep({
  report,
  onNext,
  onBack,
}: {
  report: VisibilityRunDetail | null;
  onNext: () => void;
  onBack: () => void;
}) {
  const opportunities = report?.report?.opportunities ?? [];
  const ready = report?.status === "completed";

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600, letterSpacing: "-.02em" }}>ابدأ بهاتين الخطوتين</h1>
      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
        اخترناهما بناءً على نتائج ظهور علامتك في عمليات البحث الفعلية.
      </p>

      {opportunities.length === 0 ? (
        <p style={{ marginTop: 20, fontSize: 13.5, color: "var(--mut)", lineHeight: 1.8 }}>
          {ready ? "لم نجد فجوات واضحة في ظهورك حاليًا — استمر في مراقبة ظهور علامتك." : "لا تزال الخطوات المقترحة قيد الإعداد بناءً على نتائج ظهور علامتك…"}
        </p>
      ) : (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 12 }}>
          {opportunities.map((op) => (
            <div key={op.title} style={{ border: "1px solid var(--line)", borderRadius: 14, background: "var(--panel)", padding: 16 }}>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 700, lineHeight: 1.7 }}>{op.title}</p>
              <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--mut)", lineHeight: 1.8 }}>{op.reason}</p>
              <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--dim)", lineHeight: 1.8 }}>{op.evidence}</p>
              {op.actions.length > 0 && (
                <ul style={{ margin: "8px 0 0", paddingRight: 18, fontSize: 12.5, color: "var(--tx)", lineHeight: 1.9 }}>
                  {op.actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={stepNavRow}>
        <button onClick={onBack} style={backLink}>‹ رجوع</button>
        <div style={{ flex: 1 }} />
        <button onClick={onNext} className="rl-fill-soft" style={{ ...solidBtn, width: "auto", padding: "11px 22px" }}>
          احصل على التقرير الكامل
        </button>
      </div>
    </div>
  );
}
