import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, EyeOff, Info, LockKeyhole, RotateCcwKey, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const emailSchema = z.email();
const resetPasswordSchema = z.object({
  password: z.string()
    .min(8, "Mật khẩu phải có ít nhất 8 ký tự.")
    .regex(/[A-Z]/, "Mật khẩu phải có ít nhất một chữ hoa.")
    .regex(/[a-z]/, "Mật khẩu phải có ít nhất một chữ thường.")
    .regex(/\d/, "Mật khẩu phải có ít nhất một chữ số."),
  confirmPassword: z.string().min(1, "Nhập lại mật khẩu mới."),
}).refine(({ password, confirmPassword }) => password === confirmPassword, {
  message: "Mật khẩu xác nhận không trùng khớp.",
  path: ["confirmPassword"],
});

const STRENGTH_BARS = [0, 1, 2] as const;

type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

export function ResetPasswordForm() {
  const [searchParams] = useSearchParams();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [showIntegrationNotice, setShowIntegrationNotice] = useState(false);
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmPassword: "" },
  });
  const password = form.watch("password");
  const confirmation = form.watch("confirmPassword");
  const requestedEmail = searchParams.get("email");
  const accountLabel = requestedEmail && emailSchema.safeParse(requestedEmail).success
    ? requestedEmail
    : "Email trường học";
  const strengthScore = [
    password.length >= 8,
    /[A-Z]/.test(password),
    /[a-z]/.test(password),
    /\d/.test(password),
  ].filter(Boolean).length;
  const activeBars = password.length === 0 ? 0 : strengthScore === 4 ? 3 : strengthScore >= 2 ? 2 : 1;
  const strengthLabel = password.length === 0 ? "Chưa nhập" : strengthScore === 4 ? "Mạnh" : strengthScore >= 2 ? "Trung bình" : "Yếu";
  const strengthColor = strengthScore === 4 ? "bg-emerald-500" : strengthScore >= 2 ? "bg-amber-500" : "bg-red-500";

  return (
    <section className="w-full max-w-[400px]" aria-labelledby="reset-password-title">
      <Link className="group mb-6 inline-flex items-center gap-1.5 text-[13px] font-medium text-primary hover:text-[#4837c4]" to="/login">
        <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden="true" />
        Quay lại đăng nhập
      </Link>

      <div className="mb-8">
        <div className="mb-4 grid size-10 place-items-center rounded-lg border border-primary/15 bg-primary-subtle text-primary">
          <RotateCcwKey className="size-[22px]" aria-hidden="true" />
        </div>
        <h1 id="reset-password-title" className="mb-2 text-2xl font-semibold leading-tight tracking-tight">
          Thiết lập mật khẩu mới
        </h1>
        <p className="text-sm leading-relaxed text-[#787586]">
          Nhập mật khẩu mới tối thiểu 8 ký tự, gồm chữ hoa, chữ thường và chữ số.
        </p>
        <div className="mt-3.5 flex items-center gap-2 rounded-md border border-[#e7e5e0] bg-white px-3 py-1.5 text-xs text-[#787586]">
          <ShieldCheck className="size-4 shrink-0 text-primary" aria-hidden="true" />
          <span>Tài khoản yêu cầu:</span>
          <span className="min-w-0 truncate font-medium text-[#1a1c1c]">{accountLabel}</span>
        </div>
      </div>

      {showIntegrationNotice ? (
        <Alert className="mb-5 border-primary/20 bg-primary/5 text-[#1a1c1c]">
          <Info className="text-primary" aria-hidden="true" />
          <AlertTitle className="text-primary">Chưa kết nối dịch vụ đặt lại mật khẩu</AlertTitle>
          <AlertDescription>
            Giao diện và validation đã sẵn sàng, nhưng Identity API chưa cung cấp endpoint xác nhận token. Mật khẩu chưa thay đổi.
          </AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form className="space-y-5" onSubmit={form.handleSubmit(() => setShowIntegrationNotice(true))} noValidate>
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-[13px] font-semibold text-[#1a1c1c]">Mật khẩu mới</FormLabel>
                <div className="relative">
                  <FormControl>
                    <Input
                      className="h-11 rounded-lg border-[#c8c4be] bg-white px-3.5 pr-11 shadow-none"
                      autoComplete="new-password"
                      placeholder="Nhập mật khẩu mới"
                      type={showPassword ? "text" : "password"}
                      {...field}
                    />
                  </FormControl>
                  <Button
                    className="absolute right-1 top-1 size-9 text-[#787586] hover:bg-transparent hover:text-[#1a1c1c]"
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={showPassword ? "Ẩn mật khẩu mới" : "Hiện mật khẩu mới"}
                    onClick={() => setShowPassword((visible) => !visible)}
                  >
                    {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </Button>
                </div>
                <div
                  className="mt-2.5"
                  role="meter"
                  aria-label={`Độ mạnh mật khẩu: ${strengthLabel}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={strengthScore * 25}
                >
                  <div className="mb-1.5 grid grid-cols-3 gap-1.5">
                    {STRENGTH_BARS.map((bar) => (
                      <span
                        key={bar}
                        className={cn("h-[3px] rounded-full", bar < activeBars ? strengthColor : "bg-[#e7e5e0]")}
                      />
                    ))}
                  </div>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className={cn("flex items-center gap-1 font-medium", strengthScore === 4 ? "text-emerald-600" : "text-[#787586]") }>
                      {strengthScore === 4 ? <CheckCircle2 className="size-3.5" aria-hidden="true" /> : null}
                      Độ mạnh: {strengthLabel}
                    </span>
                    <span className="text-[11px] text-[#938f9f]">{strengthScore * 25}% tiêu chuẩn bảo mật</span>
                  </div>
                </div>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-[13px] font-semibold text-[#1a1c1c]">Xác nhận mật khẩu mới</FormLabel>
                <div className="relative">
                  <FormControl>
                    <Input
                      className="h-11 rounded-lg border-[#c8c4be] bg-white px-3.5 pr-11 shadow-none"
                      autoComplete="new-password"
                      placeholder="Nhập lại mật khẩu mới"
                      type={showConfirmation ? "text" : "password"}
                      {...field}
                    />
                  </FormControl>
                  <Button
                    className="absolute right-1 top-1 size-9 text-[#787586] hover:bg-transparent hover:text-[#1a1c1c]"
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={showConfirmation ? "Ẩn mật khẩu xác nhận" : "Hiện mật khẩu xác nhận"}
                    onClick={() => setShowConfirmation((visible) => !visible)}
                  >
                    {showConfirmation ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </Button>
                </div>
                {confirmation.length > 0 && confirmation === password ? (
                  <p className="flex items-center gap-1 text-[11px] text-emerald-600">
                    <CheckCircle2 className="size-3.5" aria-hidden="true" />
                    Mật khẩu xác nhận trùng khớp
                  </p>
                ) : null}
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="pt-2">
            <Button className="h-11 w-full rounded-lg font-semibold" type="submit">
              Cập nhật mật khẩu &amp; Đăng nhập ngay
              <ArrowRight aria-hidden="true" />
            </Button>
          </div>
        </form>
      </Form>

      <div className="mt-6 flex items-start gap-2.5 rounded-lg border border-[#e7e5e0] bg-white p-3.5 text-xs leading-relaxed text-[#787586]">
        <Info className="mt-0.5 size-[18px] shrink-0 text-primary" aria-hidden="true" />
        Liên kết khôi phục chỉ nên có hiệu lực một lần trong 24 giờ. Backend phải thu hồi các phiên cũ sau khi cập nhật mật khẩu.
      </div>

      <div id="academic-support" className="mt-8 text-center">
        <p className="text-xs text-[#787586]">
          Cần hỗ trợ kỹ thuật? Liên hệ
          <strong className="font-medium text-[#1a1c1c]"> Quản trị viên khoa </strong>
          hoặc
          <strong className="font-medium text-[#1a1c1c]"> Phòng Đào tạo</strong>.
        </p>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-[11px] text-[#938f9f]">
          <span className="flex items-center gap-1">
            <LockKeyhole className="size-3.5" aria-hidden="true" />
            Mã hóa chuẩn AES-256
          </span>
          <span aria-hidden="true">•</span>
          <span className="flex items-center gap-1">
            <ShieldCheck className="size-3.5" aria-hidden="true" />
            Cổng SSO Đại học Quốc gia
          </span>
        </div>
      </div>
    </section>
  );
}
