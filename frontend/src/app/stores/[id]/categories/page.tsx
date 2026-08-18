"use client";
/* eslint-disable @next/next/no-img-element -- audited external store images */

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { IconExternal, IconMarket } from "@/components/ui/icons";
import { CategoryWorkspaceItem, getCategories } from "@/lib/api";

export default function CategoriesPage() {
  const storeId = useParams<{id:string}>().id;
  const [categories,setCategories] = useState<CategoryWorkspaceItem[]|null>(null);
  const [error,setError] = useState<string|null>(null);
  useEffect(()=>{getCategories(storeId).then((result)=>setCategories(result.categories)).catch((reason)=>setError(String(reason)));},[storeId]);
  if(error)return <ErrorState message={error}/>;
  if(!categories)return <LoadingState label="نرتب تصنيفات المنتجات..."/>;
  return <div className="flex flex-col gap-6"><header><p className="text-xs font-semibold text-primary">هيكل المتجر</p><h1 className="mt-1 text-2xl font-bold text-text">تصنيفات المنتجات</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">كل بطاقة تمثل تصنيفًا اكتشفه ظهور فعلًا. الصورة من التصنيف أو أحد منتجاته، والعدد يعكس المنتجات التي أمكن ربطها به فقط.</p></header>{categories.length===0?<EmptyState icon={<IconMarket className="h-5 w-5"/>} title="لم نكتشف تصنيفات مؤكدة بعد" description="لن ننشئ تصنيفات أو أعدادًا تقديرية من دون صفحات أو روابط متجر تدعمها."/>:<section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{categories.map((category)=><Card key={category.id} padding="none" className="overflow-hidden"><div className="aspect-[4/3] bg-neutral-tint">{category.representative_image_url?<img src={category.representative_image_url} alt="" className="h-full w-full object-cover"/>:<div className="flex h-full items-center justify-center text-text-tertiary"><IconMarket className="h-8 w-8"/></div>}</div><div className="p-5"><div className="flex items-start justify-between gap-3"><h2 className="font-bold text-text">{category.name}</h2><Badge variant="success">مؤكد</Badge></div><p className="mt-3 text-sm text-text-secondary">{category.product_count>0?`${category.product_count} منتجات مرتبطة` : "لم نتمكن من ربط عدد منتجات مؤكد"}</p>{category.url&&<a href={category.url} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary"><IconExternal className="h-4 w-4"/>فتح صفحة التصنيف</a>}</div></Card>)}</section>}</div>;
}
