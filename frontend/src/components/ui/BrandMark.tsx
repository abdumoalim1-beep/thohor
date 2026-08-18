import Image from "next/image";

export function BrandMark({ className = "h-7 w-7" }: { className?: string }) {
  return <Image src="/brand/zuhoor-mark-128.png" alt="" width={128} height={128} priority className={`${className} object-contain`} />;
}
