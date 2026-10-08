import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Eye, EyeOff, Layers3, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError } from "@/lib/api/errors";
import { isSafeInternalPath } from "@/lib/navigation/safeInternalPath";

const loginSchema = z.object({
  email: z.email("Nhập địa chỉ email hợp lệ."),
  password: z.string().min(8, "Mật khẩu phải có ít nhất 8 ký tự."),
});

type LoginValues = z.infer<typeof loginSchema>;

function safeReturnTarget(state: unknown): string {
  if (!state || typeof state !== "object" || !("returnTo" in state)
    || !isSafeInternalPath(state.returnTo)) {
    return "/my-work";
  }
  return state.returnTo;
}

export function LoginForm() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function submit(values: LoginValues) {
    setSubmitError(null);
    try {
      await auth.login(values);
      navigate(safeReturnTarget(location.state), { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        return;
      }
      setSubmitError("Không thể đăng nhập. Vui lòng thử lại.");
    }
  }

  return (
    <section className="flex w-full max-w-[400px] flex-col" aria-labelledby="login-title">
      <div className="mb-8 flex flex-col items-center text-center">
        <div className="mb-4 grid size-12 place-items-center rounded-lg bg-primary text-primary-foreground">
          <Layers3 className="size-7" aria-hidden="true" />
        </div>
        <h1 id="login-title" className="mb-2 text-2xl font-semibold leading-tight tracking-tight">
          Đăng nhập vào UTask
        </h1>
        <p className="text-sm leading-relaxed text-[#787586]">
          Nền tảng quản lý đồ án CNTT tích hợp Scrum &amp; GitHub
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <Button
          className="h-11 w-full rounded-lg border-[#c8c4be] bg-white text-sm text-[#1a1c1c] shadow-none disabled:cursor-not-allowed disabled:opacity-100"
          type="button"
          variant="outline"
          disabled
          title="Google Workspace SSO chưa khả dụng trong giai đoạn hiện tại."
        >
          <svg className="size-4" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
          </svg>
          Tiếp tục với Google
        </Button>
        <Button
          className="h-11 w-full rounded-lg border-[#c8c4be] bg-white text-sm text-[#1a1c1c] shadow-none disabled:cursor-not-allowed disabled:opacity-100"
          type="button"
          variant="outline"
          disabled
          title="GitHub SSO chưa khả dụng trong giai đoạn hiện tại."
        >
          <svg className="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
          </svg>
          Tiếp tục với GitHub
        </Button>
      </div>

      <div className="relative my-6 flex items-center">
        <div className="flex-grow border-t border-[#e5e3df]" />
        <span className="mx-3 flex-shrink-0 bg-[#faf9f8] px-1 text-xs text-[#787586]">
          hoặc đăng nhập bằng email
        </span>
        <div className="flex-grow border-t border-[#e5e3df]" />
      </div>

      {submitError ? (
        <Alert className="mb-4 border-destructive/30 bg-white" variant="destructive">
          <AlertDescription>{submitError}</AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form className="space-y-4" onSubmit={form.handleSubmit(submit)} noValidate>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-[13px] font-semibold text-[#1a1c1c]">Email trường học</FormLabel>
                <FormControl>
                  <Input
                    className="h-11 rounded-lg border-[#c8c4be] bg-white px-3.5 shadow-none"
                    autoComplete="email"
                    inputMode="email"
                    placeholder="masv@st.edu.vn hoặc giangvien@edu.vn"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-[13px] font-semibold text-[#1a1c1c]">Mật khẩu</FormLabel>
                <div className="relative">
                  <FormControl>
                    <Input
                      className="h-11 rounded-lg border-[#c8c4be] bg-white px-3.5 pr-11 shadow-none"
                      autoComplete="current-password"
                      placeholder="Nhập mật khẩu học vụ"
                      type={showPassword ? "text" : "password"}
                      {...field}
                    />
                  </FormControl>
                  <Button
                    className="absolute right-1 top-1 size-9 text-[#787586] hover:bg-transparent hover:text-[#1a1c1c]"
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    onClick={() => setShowPassword((visible) => !visible)}
                  >
                    {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </Button>
                </div>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex items-center justify-between gap-4 pt-1">
            {/* <span className="flex items-center gap-1.5 text-[13px] text-[#484649]">
              <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
              Phiên đăng nhập an toàn
            </span> */}
            <Link className="shrink-0 text-[13px] font-medium text-primary hover:underline" to="/forgot-password">
              Quên mật khẩu?
            </Link>
          </div>

          <div className="pt-2">
            <Button className="h-11 w-full rounded-lg font-semibold" type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
              {form.formState.isSubmitting ? "Đang đăng nhập" : "Đăng nhập"}
              {!form.formState.isSubmitting ? <ArrowRight aria-hidden="true" /> : null}
            </Button>
          </div>
        </form>
      </Form>
    </section>
  );
}
