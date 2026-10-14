import type { MyWorkSummary } from "@/features/my-work/types";

interface SummaryItem {
  label: string;
  value: string;
  tone: "neutral" | "primary" | "warning" | "danger";
}

function summaryItems(summary: MyWorkSummary): SummaryItem[] {
  return [
    {
      label: "việc cần làm hôm nay",
      value: String(summary.dueToday),
      tone: "neutral",
    },
    {
      label: "việc quá hạn",
      value: String(summary.overdue),
      tone: summary.overdue > 0 ? "danger" : "neutral",
    },
    {
      label: "PR chờ xử lý",
      value: String(summary.openPullRequests),
      tone: summary.openPullRequests > 0 ? "primary" : "neutral",
    },
    {
      label: "tiến độ Sprint trung bình",
      value: `${summary.sprintProgressPercent}%`,
      tone: "neutral",
    },
  ];
}

const toneClasses: Record<SummaryItem["tone"], string> = {
  neutral: "text-foreground",
  primary: "text-primary",
  warning: "text-amber-600",
  danger: "text-destructive",
};

export function DashboardSummary({ summary }: { summary: MyWorkSummary }) {
  return (
    <dl className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
      {summaryItems(summary).map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <dt className="sr-only">{item.label}</dt>
          <dd className="flex items-center gap-1.5">
            <span className={`text-sm font-bold ${toneClasses[item.tone]}`}>{item.value}</span>
            <span>{item.label}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}