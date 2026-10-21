import { useEffect, useRef, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { githubErrorMessage } from "@/features/notifications/components/RealGitHubIntegration";
import { useCompleteGitHubAuthorization, useStartGitHubAuthorization } from "@/lib/query/integrationHooks";

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
  const complete = useCompleteGitHubAuthorization();
  const restart = useStartGitHubAuthorization();
  const submittedState = useRef<string | null>(null);

  const code = params.get("code");
  const state = params.get("state");
  const denied = params.get("error");
  const valid = !denied && Boolean(code) && Boolean(state);

  useEffect(() => {
    // `state` chỉ dùng được một lần: khóa theo `state` để StrictMode chạy effect hai lần cũng không gọi lại.
    if (!valid || !code || !state || submittedState.current === state) {
      return;
    }
    submittedState.current = state;
    complete.mutate(
      { code, state },
      { onSuccess: () => navigate("/settings/integrations", { replace: true }) },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ phụ thuộc vào query của callback
  }, [valid, code, state]);

  if (denied) {
    return <Notice title="Bạn đã hủy cấp quyền GitHub." />;
  }
  if (!valid) {
    return <Notice title="Liên kết callback không hợp lệ." />;
  }
  if (complete.isError) {
    return (
      <Notice title="Không thể hoàn tất liên kết GitHub">
        <p role="alert" className="text-sm text-muted-foreground">
          {githubErrorMessage(complete.error)}
        </p>
        <Button size="sm" onClick={() => restart.mutate()} disabled={restart.isPending}>
          Thử lại liên kết
        </Button>
      </Notice>
    );
  }
  return (
    <div className="page-container px-4 pt-12 text-center text-sm text-muted-foreground" role="status">
      Đang hoàn tất liên kết GitHub…
    </div>
  );
}

export default Component;
