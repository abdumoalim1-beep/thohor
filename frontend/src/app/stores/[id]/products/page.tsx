"use client";
/* eslint-disable @next/next/no-img-element -- product images come from arbitrary audited store domains */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { IconArrowLeft, IconStore } from "@/components/ui/icons";
import { ProductWorkspaceListItem, getProducts } from "@/lib/api";

export default function ProductsPage() {
  const storeId = useParams<{ id: string }>().id;
  const [products, setProducts] = useState<ProductWorkspaceListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "issues">("all");

  useEffect(() => {
    getProducts(storeId).then((result) => setProducts(result.products)).catch((reason) => setError(String(reason)));
  }, [storeId]);

  const visible = useMemo(
    () => (products ?? []).filter((product) => filter === "all" || product.issues_count > 0),
    [filter, products],
  );

  if (error) return <ErrorState message={error} />;
  if (!products) return <LoadingState label="نجهّز صفحات المنتجات..." />;

  return <div className="flex flex-col gap-6">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-semibold text-primary">مساحة العمل</p><h1 className="mt-1 text-2xl font-bold text-text">المنتجات والصفحات</h1><p className="mt-2 text-sm text-text-secondary">اختر منتجًا لترى صفحته، مشكلاتها، والتعديلات الجاهزة بصريًا.</p></div>
      <div className="flex rounded-xl border border-border bg-white p-1 text-sm">
        <button onClick={() => setFilter("all")} className={`rounded-lg px-4 py-2 ${filter === "all" ? "bg-primary text-white" : "text-text-secondary"}`}>الكل ({products.length})</button>
        <button onClick={() => setFilter("issues")} className={`rounded-lg px-4 py-2 ${filter === "issues" ? "bg-primary text-white" : "text-text-secondary"}`}>تحتاج تحسينًا ({products.filter((p) => p.issues_count > 0).length})</button>
      </div>
    </header>

    {visible.length === 0 ? <EmptyState icon={<IconStore className="h-5 w-5" />} title="لا توجد منتجات مطابقة" description="نعرض فقط المنتجات المؤكدة التي اكتشفها ظهور من صفحات المتجر." /> :
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((product) => <Link key={product.id} href={`/stores/${storeId}/products/${product.id}`} className="group">
          <Card padding="none" className="h-full overflow-hidden transition group-hover:-translate-y-1 group-hover:border-primary/35 group-hover:shadow-lg">
            <div className="aspect-[4/3] bg-neutral-tint">{product.image_url ? <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-text-tertiary"><IconStore className="h-8 w-8" /></div>}</div>
            <div className="p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="line-clamp-2 font-bold text-text">{product.name}</h2>{product.category_name && <p className="mt-1 text-xs text-text-tertiary">{product.category_name}</p>}</div><span className={`shrink-0 text-lg font-bold ${product.completion_score >= 75 ? "text-success" : "text-primary"}`}>{product.completion_score}%</span></div>
              <div className="mt-4 flex flex-wrap gap-2"><Badge variant={product.issues_count ? "warning" : "success"}>{product.issues_count ? `${product.issues_count} عناصر تحتاج تحسينًا` : "الأساسيات مكتملة"}</Badge>{product.price !== null && <Badge variant="neutral">{product.price} {product.currency ?? ""}</Badge>}</div>
              <div className="mt-5 flex items-center justify-between border-t border-border pt-4 text-sm font-semibold text-primary"><span>افتح مساحة التحسين</span><IconArrowLeft className="h-4 w-4" /></div>
            </div>
          </Card>
        </Link>)}
      </section>}
  </div>;
}
