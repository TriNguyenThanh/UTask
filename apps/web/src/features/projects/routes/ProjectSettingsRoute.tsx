import { KeyRound, LoaderCircle, Sparkles, Users } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/ErrorState";
import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ProjectAiSettings } from "@/lib/api/studentFlow";
import { ApiError } from "@/lib/api/errors";
import { useProjectAiSettings, useSaveAiKey } from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* AI status presentation                                              */
/* ------------------------------------------------------------------ */

const aiStatusCopy: Record<
  ProjectAiSettings["ai"]["status"],
  { title: string; description: string }
> = {
  "not-configured": {
    title: "Chưa cấu hình",
    description:
      "Trưởng nhóm chưa cấu hình API key AI cho dự án. Các tính năng AI (phân tách task tự động, cảnh báo rủi ro sprint) chưa khả dụng.",
  },
  checking: {
    title: "Đang kiểm tra key",
    description: "Hệ thống đang xác minh API key với nhà cung cấp.",
  },
  connected: {
    title: "Đã kết nối",
    description:
      "API key hợp lệ. Các tính năng AI đã sẵn sàng cho Trưởng nhóm sử dụng.",
  },
  "invalid-key": {
    title: "API key không hợp lệ",
    description:
      "Key đã lưu bị từ chối bởi nhà cung cấp. Hãy nhập lại key mới bên dưới.",
  },
  "provider-unavailable": {
    title: "Nhà cung cấp tạm thời không phản hồi",
    description:
      "Không kết nối được tới nhà cung cấp AI. Hãy thử lưu lại key sau ít phút.",
  },
  "quota-exceeded": {
    title: "Đã vượt hạn mức (quota)",
    description:
      "API key đã dùng hết hạn mức của nhà cung cấp. Hãy nâng cấp gói hoặc nhập key khác.",
  },
};

const aiStatusTone: Record<ProjectAiSettings["ai"]["status"], string> = {
  "not-configured": "bg-secondary text-muted-foreground",
  checking: "bg-secondary text-muted-foreground",
  connected: "border-emerald-200 bg-emerald-50 text-emerald-800",
  "invalid-key": "border-red-200 bg-red-50 text-red-700",
  "provider-unavailable": "border-amber-200 bg-amber-50 text-amber-800",
  "quota-exceeded": "border-red-200 bg-red-50 text-red-700",
};

const aiProviders = [
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic (Claude)" },
  { id: "google", label: "Google (Gemini)" },
];

function providerLabel(provider: string): string {
  return aiProviders.find((p) => p.id === provider)?.label ?? provider;
}

/* ------------------------------------------------------------------ */
/* AI key form (leader only)                                           */
/* ------------------------------------------------------------------ */

function AiKeyForm({
  projectId,
  ai,
}: {
  projectId: string;
  ai: ProjectAiSettings["ai"];
}) {
  const [provider, setProvider] = useState(ai.provider);
  const [apiKey, setApiKey] = useState("");
  const saveAiKey = useSaveAiKey(projectId);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedKey = apiKey.trim();
    if (trimmedKey.length === 0) {
      toast.error("Vui lòng nhập API key.");
      return;
    }
    saveAiKey.mutate(
      { provider, apiKey: trimmedKey },
      {
        onSuccess: () => {
          toast.success("Đã lưu API key");
          setApiKey("");
        },
        onError: (error) => {
          const message =
            error instanceof ApiError ? error.message : "Lưu API key thất bại.";
          toast.error(message);
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="ai-provider">Nhà cung cấp AI</Label>
        <Select value={provider} onValueChange={setProvider}>
          <SelectTrigger id="ai-provider" className="w-full sm:w-64">
            <SelectValue placeholder="Chọn nhà cung cấp" />
          </SelectTrigger>
          <SelectContent>
            {aiProviders.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="ai-api-key">API key</Label>
        <Input
          id="ai-api-key"
          type="password"
          autoComplete="off"
          placeholder="sk-..."
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          aria-describedby="ai-key-help"
        />
        <p id="ai-key-help" className="text-xs text-muted-foreground">
          Key được mã hóa phía server, không lưu trên trình duyệt. Thành viên chỉ
          thấy trạng thái AI available/unavailable.
        </p>
      </div>
      <Button type="submit" size="sm" disabled={saveAiKey.isPending}>
        {saveAiKey.isPending ? (
          <>
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
            Đang lưu...
          </>
        ) : (
          "Lưu key"
        )}
      </Button>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Main route                                                          */
/* ------------------------------------------------------------------ */

export default function ProjectSettingsRoute() {
  const { projectId = "" } = useParams();
  const { data, isLoading, error, refetch } = useProjectAiSettings(projectId);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenPage />;
    }
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => void refetch()} />
      </div>
    );
  }

  if (isLoading || !data) {
    return <PageSkeleton label="Đang tải cài đặt dự án" />;
  }

  const { myRole, ai } = data;
  const statusCopy = aiStatusCopy[ai.status];
  const showKeyForm =
    myRole === "leader" &&
    (ai.status === "not-configured" ||
      ai.status === "invalid-key" ||
      ai.status === "quota-exceeded" ||
      ai.status === "provider-unavailable");

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-col items-start justify-between gap-2 md:flex-row md:items-center">
        <p className="text-sm text-muted-foreground">
          Cấu hình AI provider và quyền hạn của nhóm trong dự án.
        </p>
        <Badge
          variant="outline"
          className={cn(
            "font-semibold",
            myRole === "leader"
              ? "border-purple-200 bg-purple-50 text-primary"
              : "bg-secondary text-muted-foreground",
          )}
        >
          {myRole === "leader" ? "Trưởng nhóm" : "Thành viên"}
        </Badge>
      </div>

      {/* AI / BYOK section */}
      <section className="rounded-md border border-border bg-card">
        <div className="border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-sm font-bold">
            <Sparkles className="size-4 text-primary" aria-hidden />
            AI Assistant (BYOK)
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Bring Your Own Key: Trưởng nhóm cấu hình API key riêng của nhóm để
            bật các tính năng AI trong dự án.
          </p>
        </div>
        <div className="space-y-4 p-4">
          <div className="flex items-start gap-3">
            {ai.status === "checking" ? (
              <LoaderCircle
                className="mt-0.5 size-4 shrink-0 animate-spin text-primary"
                aria-hidden
              />
            ) : (
              <KeyRound className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
            )}
            <div>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] font-semibold",
                  aiStatusTone[ai.status],
                )}
              >
                {statusCopy.title}
              </span>
              <p className="mt-1.5 text-xs text-muted-foreground">
                {statusCopy.description}
              </p>
              {ai.keyHint !== null && ai.status === "connected" ? (
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                  Key hiện tại: {ai.keyHint}
                </p>
              ) : null}
            </div>
          </div>

          {ai.status === "connected" ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Nhà cung cấp:{" "}
                <strong className="text-foreground">
                  {providerLabel(ai.provider)}
                </strong>
              </span>
              <Button variant="outline" size="sm" disabled title="API kiểm tra kết nối sẽ khả dụng khi backend hỗ trợ">
                Kiểm tra kết nối
              </Button>
              <Button variant="outline" size="sm" disabled title="API xóa key chưa được backend hỗ trợ">
                Xóa key
              </Button>
            </div>
          ) : null}

          {showKeyForm ? <AiKeyForm projectId={projectId} ai={ai} /> : null}

          <p className="border-t border-border pt-3 text-[11px] text-muted-foreground">
            Key được mã hóa phía server, không lưu trên trình duyệt. Thành viên
            khác chỉ thấy trạng thái AI available/unavailable của dự án.
          </p>
        </div>
      </section>

      {/* Permissions section */}
      <section className="rounded-md border border-border bg-card">
        <div className="border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-sm font-bold">
            <Users className="size-4 text-primary" aria-hidden />
            Quyền hạn trong dự án
          </h2>
        </div>
        <div className="grid gap-4 p-4 md:grid-cols-2">
          <div className="rounded-md border border-purple-200 bg-purple-50/50 p-3">
            <h3 className="text-xs font-semibold text-primary">Trưởng nhóm</h3>
            <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
              <li>• Tạo và giao Issue, quản lý Backlog, Sprint và Epic</li>
              <li>• Cấu hình API key AI (BYOK) cho cả nhóm</li>
              <li>• Duyệt thay đổi quan trọng và quản lý cài đặt dự án</li>
            </ul>
          </div>
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <h3 className="text-xs font-semibold">Thành viên</h3>
            <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
              <li>• Xem Backlog, Bảng công việc và thống kê mã nguồn</li>
              <li>• Cập nhật trạng thái Issue được giao, comment công việc</li>
              <li>
                • Không thấy API key AI — chỉ thấy trạng thái AI
                available/unavailable
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
export function Component() {
  return <ProjectSettingsRoute />;
}
