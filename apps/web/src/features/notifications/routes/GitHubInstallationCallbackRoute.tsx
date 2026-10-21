import { useEffect, useRef, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { githubErrorMessage } from "@/features/notifications/components/RealGitHubIntegration";
import { useCompleteGitHubInstallation, useStartGitHubInstallation } from "@/lib/query/integrationHooks";

const SETUP_ACTIONS = ["install", "update", "request"];

function Notice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="page-container mx-auto max-w-lg space-y-4 px-4 pt-12 text-center" role="status">
      <h1 className="text-lg font-semibold">{title}</h1>
      {children}
      <Button asChild variant="outline" size="sm">
        <Link to="/settings/integrations">Về trang tích hợp</Link>
      </Button>
    </div>
  );
}

export function Component() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const complete = useCompleteGitHubInstallation();
  const restart = useStartGitHubInstallation();
  const submittedState = useRef<string | null>(null);

  const installationId = params.get("installation_id");
  const setupAction = params.get("setup_action");
  const state = params.get("state");

  // Chủ tổ chức chưa duyệt: GitHub chỉ trả `setup_action=request`, chưa có `installation_id`.
  const requested = setupAction === "request" && !installationId;
  const valid =
    !requested && Boolean(state) && setupAction !== null && SETUP_ACTIONS.includes(setupAction) && Boolean(installationId);

  useEffect(() => {
    // `state` chỉ dùng được một lần: khóa theo `state` để StrictMode chạy effect hai lần cũng không gọi lại.
    if (!valid || !state || !installationId || !setupAction || submittedState.current === state) {
      return;
    }
    submittedState.current = state;
    complete.mutate(
      { state, installation_id: installationId, setup_action: setupAction },
      {
        onSuccess: (result) => {
          if (result.status === "ACTIVE") {
            navigate("/settings/integrations", { replace: true });
          }
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ phụ thuộc vào query của callback
  }, [valid, state, installationId, setupAction]);

  if (requested) {
    return <Notice title="Đã gửi yêu cầu cài đặt, chờ chủ tổ chức duyệt." />;
  }
  if (!valid) {
    return <Notice title="Liên kết callback không hợp lệ." />;
  }
  if (complete.data?.status === "PENDING_APPROVAL") {
    return <Notice title="Yêu cầu cài đặt đang chờ chủ tổ chức duyệt." />;
  }
  if (complete.isError) {
    return (
      <Notice title="Không thể hoàn tất cài đặt GitHub App">
        <p role="alert" className="text-sm text-muted-foreground">
          {githubErrorMessage(complete.error)}
        </p>
        <Button
          size="sm"
          onClick={() => restart.mutate(undefined, { onError: (error) => toast.error(githubErrorMessage(error)) })}
          disabled={restart.isPending}
        >
          Thử lại cài đặt
        </Button>
      </Notice>
    );
  }
  return (
    <div className="page-container px-4 pt-12 text-center text-sm text-muted-foreground" role="status">
      Đang hoàn tất cài đặt GitHub App…
    </div>
  );
}

export default Component;
