"use client";

import { useState } from "react";

import type { StoreProfile } from "@/lib/api";
import { Button } from "./Button";
import { Card } from "./Card";
import { IconCheckCircle, IconExternal, IconStore } from "./icons";

const LANGUAGE_LABELS: Record<string, string> = { ar: "العربية", en: "الإنجليزية" };
const COUNTRY_LABELS: Record<string, string> = { sa: "السعودية", ae: "الإمارات", us: "الولايات المتحدة" };

export function StoreProfileCard({ profile }: { profile: StoreProfile }) {
  const [confirmed, setConfirmed] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
  const initials = profile.name.trim().slice(0, 2).toUpperCase();
  const categories = profile.primary_categories.length > 0 ? profile.primary_categories : profile.categories.map((item) => item.name);

  return (
    <section aria-labelledby="store-profile-heading" className="overflow-hidden rounded-2xl border border-border bg-surface shadow-[var(--shadow-card)]">
      <div className="border-b border-border bg-[linear-gradient(135deg,var(--color-primary-tint),var(--color-surface)_62%)] p-5 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary text-lg font-bold text-on-primary shadow-[var(--shadow-soft)]">
              {initials || <IconStore className="h-6 w-6" />}
            </div>
            <div className="min-w-0">
              <p className="mb-1 text-xs font-semibold text-primary">متجرك</p>
              <h1 id="store-profile-heading" className="truncate text-2xl font-bold text-text">{profile.name}</h1>
              <a href={`https://${profile.domain}`} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-text-secondary hover:text-primary">
                <span dir="ltr">{profile.domain}</span>
                <IconExternal className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.country && <ProfileChip>{COUNTRY_LABELS[profile.country] ?? profile.country.toUpperCase()}</ProfileChip>}
            {profile.language && <ProfileChip>{LANGUAGE_LABELS[profile.language] ?? profile.language.toUpperCase()}</ProfileChip>}
            {profile.platform && <ProfileChip>{profile.platform}</ProfileChip>}
          </div>
        </div>

        {(profile.business_type || profile.description) && (
          <div className="mt-5 max-w-3xl">
            <p className="text-xs font-medium text-text-tertiary">متجر متخصص في</p>
            {profile.business_type && <p className="mt-1 text-lg font-semibold text-text">{profile.business_type}</p>}
            {profile.description && <p className="mt-1 line-clamp-2 text-sm text-text-secondary">{profile.description}</p>}
          </div>
        )}

        {categories.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {categories.slice(0, 4).map((category) => <ProfileChip key={category}>{category}</ProfileChip>)}
          </div>
        )}
      </div>

      <div className="p-5 sm:p-7">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {profile.products_count !== null && <ProfileMetric value={profile.products_count} label="منتجًا تعرفنا عليه" />}
          {profile.categories_count !== null && <ProfileMetric value={profile.categories_count} label="تصنيفًا" />}
          {profile.brands_count !== null && <ProfileMetric value={profile.brands_count} label="علامة مؤكدة" />}
          <ProfileMetric value={profile.pages_count} label="صفحة استطعنا قراءتها" />
        </div>

        {profile.products.length > 0 ? (
          <div className="mt-7">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-text">بعض المنتجات التي تعرفنا عليها</h2>
              {profile.products_count !== null && profile.products_count > profile.products.length && (
                <span className="text-xs text-text-tertiary">عينة من {profile.products_count}</span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {profile.products.slice(0, 6).map((product) => (
                <a key={product.url} href={product.url} target="_blank" rel="noreferrer" className="group min-w-0">
                  <div className="aspect-square overflow-hidden rounded-xl border border-border bg-bg-subtle">
                    {product.image_url ? (
                      // Product JSON-LD is the evidence source; never substitute a guessed image.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={product.image_url} alt="" className="h-full w-full object-cover transition-transform group-hover:scale-[1.03]" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-text-tertiary"><IconStore className="h-6 w-6" /></div>
                    )}
                  </div>
                  <p className="mt-2 line-clamp-2 text-xs font-medium leading-5 text-text">{product.name}</p>
                </a>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-6 rounded-xl border border-dashed border-border-strong bg-bg-subtle px-4 py-4 text-sm text-text-secondary">
            لم نتمكن من قراءة قائمة المنتجات بعد.
          </div>
        )}

        {profile.products_count === null && profile.products.length > 0 && (
          <p className="mt-3 text-xs text-text-tertiary">تعرفنا على هذه العينات، لكن لا نملك عددًا موثوقًا لكل منتجات المتجر بعد.</p>
        )}

        <div className="mt-7 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
          <div>
            <p className="text-sm font-semibold text-text">هل فهمنا متجرك بشكل صحيح؟</p>
            {editingNote && <p className="mt-1 text-xs text-text-tertiary">سنضيف حفظ التصحيحات بعد توفير سجل موثوق لها. لم نغيّر بياناتك الآن.</p>}
          </div>
          {confirmed ? (
            <span className="inline-flex items-center gap-2 text-sm font-medium text-success"><IconCheckCircle className="h-4 w-4" /> نعم، هذا متجري</span>
          ) : (
            <div className="flex gap-2">
              <Button size="sm" onClick={() => setConfirmed(true)}>نعم، أكمل التحليل</Button>
              <Button size="sm" variant="ghost" onClick={() => setEditingNote(true)}>تعديل</Button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ProfileChip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-border bg-surface/85 px-3 py-1.5 text-xs font-medium text-text-secondary">{children}</span>;
}

function ProfileMetric({ value, label }: { value: number; label: string }) {
  return (
    <Card padding="sm" className="min-w-0 bg-bg-subtle/60">
      <p className="text-2xl font-bold tabular-nums text-text">{value.toLocaleString("ar")}</p>
      <p className="mt-1 text-xs leading-5 text-text-secondary">{label}</p>
    </Card>
  );
}
