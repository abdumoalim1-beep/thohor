"use client";

import { useEffect, useState } from "react";

import { listPreviewReportLeads, type PreviewReportLeadItem } from "@/lib/api";

const ADMIN_TOKEN_STORAGE_KEY = "zuhoor_admin_token";

// Same pattern as /preview's bypass-token link: visiting once with
// ?token=... persists it to localStorage, so every later visit to this
// page (no query param needed) keeps working from the same browser.
function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  const fromUrl = new URLSearchParams(window.location.search).get("token");
  if (fromUrl && fromUrl.trim()) {
    window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, fromUrl.trim());
    return fromUrl.trim();
  }
  return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY);
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ar-SA", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function AdminLeadsPage() {
  const [leads, setLeads] = useState<PreviewReportLeadItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getAdminToken();
    if (!token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError("ما فيه رمز دخول محفوظ بهذا المتصفح — افتح الرابط اللي فيه ?token=... مرة وحدة.");
      return;
    }
    listPreviewReportLeads(token)
      .then(setLeads)
      .catch((err) => setError(err instanceof Error ? err.message : "تعذّر تحميل البيانات"));
  }, []);

  return (
    <div dir="rtl" style={{ minHeight: "100vh", background: "#f6f6f7", padding: "32px 24px", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ maxWidth: 1000, margin: "0 auto" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>طلبات الانضمام للنسخة التجريبية</h1>
        <p style={{ marginTop: 6, fontSize: 13.5, color: "#6b7280" }}>
          {leads ? `${leads.length} طلب إجمالاً` : "..."}
        </p>

        {error && (
          <div style={{ marginTop: 20, padding: 16, borderRadius: 12, background: "#fef2f2", color: "#991b1b", fontSize: 13.5 }}>
            {error}
          </div>
        )}

        {leads && (
          <div style={{ marginTop: 20, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 16, overflow: "hidden" }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.2fr 1.6fr 1.4fr 1fr 1.4fr 1fr",
                gap: 10,
                padding: "12px 16px",
                background: "#f9fafb",
                fontSize: 11.5,
                fontWeight: 700,
                color: "#6b7280",
                borderBottom: "1px solid #e5e7eb",
              }}
            >
              <span>الاسم</span>
              <span>البريد</span>
              <span>الإجابة الأولى</span>
              <span>مستوى الاهتمام</span>
              <span>المتجر</span>
              <span>التاريخ</span>
            </div>
            {leads.length === 0 && (
              <div style={{ padding: 24, fontSize: 13.5, color: "#6b7280", textAlign: "center" }}>ما فيه طلبات لحد الآن</div>
            )}
            {leads.map((lead) => (
              <div
                key={lead.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1.2fr 1.6fr 1.4fr 1fr 1.4fr 1fr",
                  gap: 10,
                  padding: "12px 16px",
                  fontSize: 13,
                  borderBottom: "1px solid #f1f1f3",
                  alignItems: "center",
                }}
              >
                <span style={{ fontWeight: 600 }}>{lead.name}</span>
                <span dir="ltr" style={{ textAlign: "right", color: "#374151" }}>{lead.email}</span>
                <span style={{ color: "#374151" }}>{lead.report_feedback}</span>
                <span style={{ color: "#374151" }}>{lead.interest_level}</span>
                <span dir="ltr" style={{ textAlign: "right", color: lead.store_url ? "#374151" : "#9ca3af" }}>
                  {lead.store_url ?? "بدون تحليل (زر الهيدر)"}
                </span>
                <span style={{ color: "#9ca3af", fontSize: 11.5 }}>{formatDate(lead.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
