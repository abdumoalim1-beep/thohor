import { Button } from "./Button";
import { EmptyState } from "./States";
import { IconAlertTriangle, IconInfoCircle } from "./icons";

export function FailedResearchState({
  reason,
  onRetry,
  retrying,
}: {
  reason: string | null;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <EmptyState
      icon={<IconAlertTriangle className="h-5 w-5 text-danger" />}
      title="تعذر إكمال تحليل متجرك"
      description={reason ?? "حدث خطأ أثناء التحليل. يمكنك إعادة المحاولة الآن."}
      action={
        <Button className="mt-2" onClick={onRetry} disabled={retrying}>
          {retrying ? "جارٍ إعادة المحاولة..." : "إعادة المحاولة"}
        </Button>
      }
    />
  );
}

export function CancelledResearchState() {
  return (
    <EmptyState
      title="تم إيقاف التحليل"
      description="لم نعتمد النتائج الجزئية لهذا التشغيل كنتيجة نهائية."
    />
  );
}

export function StalledResearchState({ onCheckAgain }: { onCheckAgain: () => void }) {
  return (
    <EmptyState
      icon={<IconInfoCircle className="h-5 w-5" />}
      title="يبدو أن التحليل متوقف"
      description="لم يصل أي تقدم جديد منذ مدة أطول من المتوقع. أوقفنا التحديث التلقائي حتى لا تبقى الصفحة في انتظار بلا نهاية."
      action={
        <Button className="mt-2" variant="secondary" onClick={onCheckAgain}>
          التحقق مرة أخرى
        </Button>
      }
    />
  );
}
