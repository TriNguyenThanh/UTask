import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, BadgeCheck, KeyRound, LockKeyhole, School, Send, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";

const forgotPasswordSchema = z.object({
  email: z.email("Nhập địa chỉ email trường học hợp lệ."),
});

type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export function ForgotPasswordForm() {
  const [showIntegrationNotice, setShowIntegrationNotice] = useState(false);
  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  return (
    <section className="w-full max-w-[400px]" aria-labelledby="forgot-password-title">
      <Link
        className="group mb-6 inline-flex items-center gap-1.5 text-[13px] font-medium text-primary hover:text-[#4837c4]"
        to="/login"
      >
        <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden="true" />
        Quay lại đăng nhập
      </Link>

      <div className="mb-6">
        <div className="mb-3 grid size-11 place-items-center rounded-lg bg-primary-subtle text-primary">
          <KeyRound className="size-6" aria-hidden="true" />
        </div>
        <h1 id="forgot-password-title" className="mb-2 text-2xl font-semibold tracking-tight">
          Quên mật khẩu?
        </h1>
        <p className="text-sm leading-relaxed text-[#787586]">
          Nhập địa chỉ email trường học đã liên kết với tài khoản UTask. Hướng dẫn khôi phục sẽ được gửi đến hòm thư của bạn khi dịch vụ Identity được kết nối.
        </p>
      </div>

      {showIntegrationNotice ? (
        <Alert className="mb-5 border-primary/20 bg-primary/5 text-[#1a1c1c]">
          <ShieldCheck className="text-primary" aria-hidden="true" />
          <AlertTitle className="text-primary">Chưa kết nối dịch vụ khôi phục</AlertTitle>
          <AlertDescription>
            Giao diện đã sẵn sàng, nhưng Identity API chưa cung cấp endpoint gửi email. Không có email nào được gửi.
          </AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form
          className="mb-6 space-y-4"
          onSubmit={form.handleSubmit(() => setShowIntegrationNotice(true))}
          noValidate
        >
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-[13px] font-semibold text-[#1a1c1c]">Email trường học</FormLabel>
                <div className="relative">
                  <FormControl>
                    <Input
                      className="h-11 rounded-lg border-[#c8c4be] bg-white px-3.5 pr-11 shadow-none"
                      autoComplete="email"
                      inputMode="email"
                      placeholder="masv@st.edu.vn hoặc giangvien@edu.vn"
                      {...field}
                    />
                  </FormControl>
                  <School className="pointer-events-none absolute right-3.5 top-1/2 size-[18px] -translate-y-1/2 text-[#787586]" aria-hidden="true" />
                </div>
                <p className="flex items-start gap-1 text-[11.5px] leading-relaxed text-[#787586]">
                  <BadgeCheck className="mt-0.5 size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
                  Dùng email trường đã liên kết với tài khoản UTask.
                </p>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button className="h-11 w-full rounded-lg font-medium" type="submit">
            Gửi liên kết khôi phục
            <Send aria-hidden="true" />
          </Button>
        </form>
      </Form>

      <div className="mb-6 border-t border-[#ede9e4]" />

      <div id="academic-support" className="text-center">
        <p className="text-xs leading-relaxed text-[#787586]">
          Nếu không còn quyền truy cập email trường hoặc tài khoản chưa kích hoạt, vui lòng liên hệ
          <strong className="font-medium text-[#1a1c1c]"> Giảng viên bộ môn </strong>
          hoặc
          <strong className="font-medium text-[#1a1c1c]"> Phòng Đào tạo</strong>.
        </p>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[11px] text-[#9c97a8]">
          <span className="flex items-center gap-1">
            <LockKeyhole className="size-3.5" aria-hidden="true" />
            Mã hóa SSL 256-bit
          </span>
          <span aria-hidden="true">•</span>
          <span className="flex items-center gap-1">
            <ShieldCheck className="size-3.5" aria-hidden="true" />
            Đồng bộ Cổng Đào tạo
          </span>
        </div>
      </div>
    </section>
  );
}
