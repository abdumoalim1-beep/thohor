"use client";

import { useState } from "react";

import { Button } from "./Button";
import { Card } from "./Card";
import { FEEDBACK_ISSUE_LABELS } from "./labels";

export function FeedbackModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (issues: string[], note: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (key: string) => {
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(selected, note.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <Card padding="lg" className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-base font-bold text-text">ما الذي لم نفهمه بشكل صحيح؟</h2>
        <p className="mt-1 text-sm text-text-secondary">اختر كل ما ينطبق — سيساعدنا هذا على تحسين الفهم لاحقًا.</p>

        <div className="mt-4 flex flex-col gap-2">
          {Object.entries(FEEDBACK_ISSUE_LABELS).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2.5 rounded-md border border-border px-3 py-2 text-sm text-text hover:bg-surface-hover">
              <input type="checkbox" checked={selected.includes(key)} onChange={() => toggle(key)} className="h-4 w-4 accent-primary" />
              {label}
            </label>
          ))}
        </div>

        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="تفاصيل إضافية (اختياري)"
          rows={3}
          className="mt-3 w-full resize-none rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text outline-none focus:border-primary"
        />

        {error && <p className="mt-2 text-sm text-danger">{error}</p>}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            إلغاء
          </Button>
          <Button size="sm" onClick={handleSubmit} disabled={submitting || selected.length === 0}>
            {submitting ? "جارٍ الإرسال..." : "إرسال"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
