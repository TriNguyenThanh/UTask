import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { DisabledAction } from "@/features/teacher/components/shared";

export const ADD_STUDENT_UNAVAILABLE =
  "Thêm sinh viên chưa khả dụng: chưa có hợp đồng API thêm sinh viên vào lớp. Thông tin bạn nhập chưa được gửi đi và không có tài khoản nào được tạo.";

const schema = z
  .object({
    email: z
      .string()
      .trim()
      .refine((value) => value === "" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value), "Email sai định dạng."),
    studentId: z.string().trim().max(30, "Mã sinh viên tối đa 30 ký tự."),
    lastName: z.string().trim().max(80, "Tối đa 80 ký tự."),
    firstName: z.string().trim().max(40, "Tối đa 40 ký tự."),
  })
  .superRefine((values, ctx) => {
    if (values.email === "" && values.studentId === "") {
      ctx.addIssue({
        code: "custom",
        path: ["email"],
        message: "Nhập email hoặc mã sinh viên để xác định người cần thêm.",
      });
    }
  });

type Values = z.infer<typeof schema>;

/**
 * Add one student. The form checks the format of what is typed; deciding
 * whether the person already has an account, is a teacher, or is already in
 * the class is the backend's job. No password is asked for or generated, and
 * nothing here places the student in a team.
 */
export function AddStudentDialog({ courseName }: { courseName: string }) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", studentId: "", lastName: "", firstName: "" },
    mode: "onChange",
  });

  return (
    <Dialog onOpenChange={(open) => !open && form.reset()}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          Thêm sinh viên
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Thêm sinh viên vào lớp</DialogTitle>
          <DialogDescription>
            Lớp: {courseName}. Hệ thống đối chiếu tài khoản thật, không phải giao diện này.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form noValidate onSubmit={(event) => event.preventDefault()} className="space-y-4">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" autoComplete="off" placeholder="sinhvien@truong.edu.vn" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="studentId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mã sinh viên (MSSV)</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" {...field} />
                  </FormControl>
                  <FormDescription>Chỉ có MSSV: chỉ tìm được tài khoản có sẵn.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="lastName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Họ và tên đệm</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="firstName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tên</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-950">
              {ADD_STUDENT_UNAVAILABLE}
            </p>
            <DialogFooter>
              <DisabledAction reason={ADD_STUDENT_UNAVAILABLE} variant="default">
                Thêm vào lớp
              </DisabledAction>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
