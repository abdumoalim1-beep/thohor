import { redirect } from "next/navigation";

export default async function LegacyProductPage({
  params,
}: {
  params: Promise<{ id: string; productId: string }>;
}) {
  const { id, productId } = await params;
  redirect(`/stores/${id}/products/${productId}`);
}
