import { Skeleton } from "@/components/ui/skeleton";

export function PageSkeleton({ label = "Đang tải nội dung" }: { label?: string }) {
  return (
    <div className="space-y-6 p-6" role="status" aria-label={label}>
      <Skeleton className="h-9 w-64" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}
