import { CheckCircle2, MailQuestion, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthStatusCard } from "@/features/auth/components/AuthStatusCard";
import {
  activationErrorMessage,
  NEUTRAL_RECOVERY_MESSAGE,
  recoveryErrorMessage,
} from "@/features/auth/errorMessages";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { ApiError } from "@/lib/api/errors";
import { activate, resendActivation } from "@/lib/api/identity/endpoints";

export const ACTIVATED_NOTICE = "Kích hoạt thành công. Hãy đăng nhập.";

function ResendActivation() {
  const client = useApiClient();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    try {
      await resendActivation(client, email.trim());
      setMessage({ text: NEUTRAL_RECOVERY_MESSAGE, ok: true });
    } catch (error) {
      setMessage({
        text: error instanceof ApiError ? recoveryErrorMessage(error) : "Không thể gửi yêu cầu. Vui lòng thử lại.",
        ok: false,
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="mt-6 space-y-3 border-t pt-4" onSubmit={submit}>
      <Label htmlFor="resend-email">Gửi lại email kích hoạt</Label>
      <Input
        id="resend-email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <Button type="submit" variant="outline" disabled={pending || email.trim() === ""}>
        Gửi lại email kích hoạt
      </Button>
      {message ? (
        <p className={message.ok ? "text-sm text-emerald-700" : "text-sm text-destructive"} role="status">
          {message.text}
        </p>
      ) : null}
    </form>
  );
}

export function ActivateAccountForm({ activationKey }: { activationKey: string }) {
  const client = useApiClient();
  const navigate = useNavigate();
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setFailure(null);
    try {
      // Mật khẩu chỉ gửi khi người dùng điền (tài khoản do giảng viên tạo chưa có mật khẩu).
      const withPassword = password1 !== "" || password2 !== "";
      await activate(client, {
        key: activationKey,
        ...(withPassword ? { new_password1: password1, new_password2: password2 } : {}),
      });
      navigate("/login", { replace: true, state: { notice: ACTIVATED_NOTICE } });
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught);
      } else {
        setFailure("Không thể kích hoạt. Vui lòng thử lại.");
      }
    } finally {
      setPending(false);
    }
  }

  const alreadyActive = error?.code === "ACCOUNT_ALREADY_ACTIVE";
  const linkBroken = error?.code === "RESOURCE_NOT_FOUND" || error?.code === "INVALID_ACTIVATION_TOKEN";
  const passwordErrors = [error?.fieldErrors.new_password1, error?.fieldErrors.new_password2].flat().filter(Boolean);

  if (alreadyActive) {
    return (
      <AuthStatusCard
        icon={CheckCircle2}
        title="Tài khoản đã kích hoạt"
        actions={<Link className="text-primary hover:underline" to="/login">Đăng nhập</Link>}
      >
        {activationErrorMessage(error)}
      </AuthStatusCard>
    );
  }

  return (
    <section className="w-full max-w-[400px]" aria-labelledby="activate-title">
      <div className="mb-3 grid size-11 place-items-center rounded-lg bg-primary-subtle text-primary">
        {linkBroken ? <TriangleAlert className="size-6" aria-hidden="true" /> : <MailQuestion className="size-6" aria-hidden="true" />}
      </div>
      <h1 id="activate-title" className="mb-2 text-2xl font-semibold tracking-tight">
        Kích hoạt tài khoản
      </h1>

      {error || failure ? (
        <Alert className="mb-4 border-destructive/30 bg-white" variant="destructive">
          <AlertDescription>{error ? activationErrorMessage(error) : failure}</AlertDescription>
        </Alert>
      ) : null}

      {!linkBroken ? (
        <form className="space-y-4" onSubmit={submit}>
          <p className="text-sm text-[#787586]">Nhấn nút bên dưới để hoàn tất kích hoạt tài khoản.</p>
          <details className="rounded-lg border p-3 text-sm">
            <summary className="cursor-pointer font-medium">Tài khoản do giảng viên tạo? Đặt mật khẩu</summary>
            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="activate-password1">Mật khẩu mới</Label>
                <Input
                  id="activate-password1"
                  type="password"
                  autoComplete="new-password"
                  value={password1}
                  onChange={(event) => setPassword1(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="activate-password2">Xác nhận mật khẩu mới</Label>
                <Input
                  id="activate-password2"
                  type="password"
                  autoComplete="new-password"
                  value={password2}
                  onChange={(event) => setPassword2(event.target.value)}
                />
              </div>
              {passwordErrors.length > 0 ? (
                <p className="text-xs text-destructive" role="alert">{passwordErrors.join(" ")}</p>
              ) : null}
            </div>
          </details>
          <Button className="h-11 w-full rounded-lg font-semibold" type="submit" disabled={pending}>
            Kích hoạt tài khoản
          </Button>
        </form>
      ) : null}

      <ResendActivation />
    </section>
  );
}
