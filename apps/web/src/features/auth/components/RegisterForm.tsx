import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Loader2, MailCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { AuthStatusCard } from "@/features/auth/components/AuthStatusCard";
import { recoveryErrorMessage } from "@/features/auth/errorMessages";
import { applyFieldErrors } from "@/features/auth/formErrors";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { ApiError } from "@/lib/api/errors";
import { register } from "@/lib/api/identity/endpoints";

const registerSchema = z
  .object({
    last_name: z.string().trim().min(1, "Nhập họ và tên đệm."),
    first_name: z.string().trim().min(1, "Nhập tên."),
    username: z.string().trim().min(1, "Nhập tên đăng nhập."),
    email: z.email("Nhập địa chỉ email hợp lệ."),
    password1: z.string().min(8, "Mật khẩu phải có ít nhất 8 ký tự."),
    password2: z.string().min(1, "Nhập lại mật khẩu."),
  })
  .refine((values) => values.password1 === values.password2, {
    message: "Mật khẩu xác nhận không trùng khớp.",
    path: ["password2"],
  });

type RegisterValues = z.infer<typeof registerSchema>;

const FIELDS: { name: keyof RegisterValues; label: string; type?: string; autoComplete: string }[] = [
  { name: "last_name", label: "Họ và tên đệm", autoComplete: "family-name" },
  { name: "first_name", label: "Tên", autoComplete: "given-name" },
  { name: "username", label: "Tên đăng nhập", autoComplete: "username" },
  { name: "email", label: "Email", type: "email", autoComplete: "email" },
  { name: "password1", label: "Mật khẩu", type: "password", autoComplete: "new-password" },
  { name: "password2", label: "Xác nhận mật khẩu", type: "password", autoComplete: "new-password" },
];

export function RegisterForm() {
  const client = useApiClient();
  const [registered, setRegistered] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { last_name: "", first_name: "", username: "", email: "", password1: "", password2: "" },
  });

  async function submit(values: RegisterValues) {
    setSubmitError(null);
    try {
      await register(client, values);
      setRegistered(true);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setSubmitError("Không thể đăng ký. Vui lòng thử lại.");
        return;
      }
      const shown = applyFieldErrors(
        form,
        error,
        Object.fromEntries(FIELDS.map(({ name }) => [name, name])) as Record<string, keyof RegisterValues>,
      );
      if (!shown) {
        setSubmitError(recoveryErrorMessage(error));
      }
    }
  }

  if (registered) {
    return (
      <AuthStatusCard
        icon={MailCheck}
        title="Đăng ký thành công"
        actions={<Link className="text-primary hover:underline" to="/login">Về trang đăng nhập</Link>}
      >
        Kiểm tra email để kích hoạt tài khoản. Bạn chưa thể đăng nhập cho đến khi kích hoạt.
      </AuthStatusCard>
    );
  }

  return (
    <section className="w-full max-w-[400px]" aria-labelledby="register-title">
      <h1 id="register-title" className="mb-2 text-2xl font-semibold tracking-tight">
        Đăng ký tài khoản
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">Tạo tài khoản sinh viên UTask bằng email trường.</p>

      {submitError ? (
        <Alert className="mb-4 border-destructive/30 bg-white" variant="destructive">
          <AlertDescription>{submitError}</AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form className="space-y-4" onSubmit={form.handleSubmit(submit)} noValidate>
          {FIELDS.map(({ name, label, type, autoComplete }) => (
            <FormField
              key={name}
              control={form.control}
              name={name}
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-[13px] font-semibold text-[#1a1c1c]">{label}</FormLabel>
                  <FormControl>
                    <Input
                      className="h-11 rounded-lg border-[#c8c4be] bg-white px-3.5 shadow-none"
                      type={type}
                      autoComplete={autoComplete}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
          <Button className="h-11 w-full rounded-lg font-semibold" type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
            Đăng ký
            {!form.formState.isSubmitting ? <ArrowRight aria-hidden="true" /> : null}
          </Button>
        </form>
      </Form>

      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        Đã có tài khoản?{" "}
        <Link className="font-medium text-primary hover:underline" to="/login">Đăng nhập</Link>
      </p>
    </section>
  );
}
