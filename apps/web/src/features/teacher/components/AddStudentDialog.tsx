import { zodResolver } from "@hookform/resolvers/zod";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
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
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import { isValidEmail } from "@/features/teacher/lib/csvImport";
import { describeResult, toStudentRow } from "@/features/teacher/lib/importRun";
import type { ImportRowResultDto } from "@/lib/api/classroom/dto";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { TeacherCourseDetail } from "@/lib/api/teacherFlow";
import { useAddStudents } from "@/lib/query/teacherClassHooks";
import { cn } from "@/lib/utils";

export const ADD_STUDENT_UNAVAILABLE =
  "Thêm sinh viên chưa khả dụng với dữ liệu mẫu: không có tài khoản nào được tạo và không có gì được gửi đi.";

export const addStudentSchema = z
  .object({
    email: z
      .string()
      .trim()
      .refine((value) => value === "" || isValidEmail(value), "Email sai định dạng."),
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

export type AddStudentValues = z.infer<typeof addStudentSchema>;

const EMPTY: AddStudentValues = { email: "", studentId: "", lastName: "", firstName: "" };

const TONE_STYLE = {
  success: "bg-emerald-50 text-emerald-950",
  neutral: "bg-slate-50 text-slate-800",
  problem: "bg-red-50 text-red-900",
} as const;

function OutcomeBox({ result }: Readonly<{ result: ImportRowResultDto }>) {
  const outcome = describeResult(result);
  return (
    <div role="status" className={cn("space-y-1 rounded-md px-3 py-2 text-sm", TONE_STYLE[outcome.tone])}>
      <p className="font-semibold">{outcome.label}</p>
      {outcome.detail ? <p className="text-xs">{outcome.detail}</p> : null}
    </div>
  );
}

/**
 * Add one student. The form checks the format of what is typed; deciding
 * whether the person already has an account, is a teacher, or is already in
 * the class is the backend's job. No password is asked for or generated, and
 * nothing here places the student in a team. With demo data nothing is sent.
 */
export function AddStudentDialog({ course }: Readonly<{ course: TeacherCourseDetail }>) {
  const form = useForm<AddStudentValues>({
    resolver: zodResolver(addStudentSchema),
    defaultValues: EMPTY,
    mode: "onChange",
  });
  const add = useAddStudents(course.courseId);
  const [result, setResult] = useState<ImportRowResultDto | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // Same values → same key, so a retry after a lost response cannot enroll twice.
  const attempt = useRef<{ signature: string; key: string } | null>(null);
  const isReal = course.classroom !== undefined;

  function reset() {
    form.reset(EMPTY);
    setResult(null);
    setFailure(null);
    attempt.current = null;
  }

  function submit(values: AddStudentValues) {
    // Demo data: pressing Enter must not send anything.
    if (!isReal) return;
    const students = [
      toStudentRow({
        rowNumber: 1,
        email: values.email,
        studentId: values.studentId,
        firstName: values.firstName,
        lastName: values.lastName,
      }),
    ];
    const signature = JSON.stringify(students);
    if (attempt.current?.signature !== signature) {
      attempt.current = { signature, key: newIdempotencyKey() };
    }
    setFailure(null);
    add.mutate(
      { students, idempotencyKey: attempt.current.key },
      {
        onSuccess: (data) => {
          const row = data.results[0];
          setResult(row);
          if (row && row.enrollment_result !== "FAILED") toast.success("Đã xử lý sinh viên.");
        },
        onError: (error) => setFailure(classErrorMessage(error)),
      },
    );
  }

  return (
    <Dialog onOpenChange={(open) => !open && reset()}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          Thêm sinh viên
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Thêm sinh viên vào lớp</DialogTitle>
          <DialogDescription>
            Lớp: {course.name}. Hệ thống đối chiếu tài khoản thật, không phải giao diện này.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form noValidate onSubmit={form.handleSubmit(submit)} className="space-y-4">
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
            {isReal ? null : (
              <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-950">{ADD_STUDENT_UNAVAILABLE}</p>
            )}
            {failure ? (
              <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-900">
                {failure}
              </p>
            ) : null}
            {result ? <OutcomeBox result={result} /> : null}
            <DialogFooter>
              {result ? (
                <Button type="button" variant="outline" onClick={reset}>
                  Thêm người khác
                </Button>
              ) : null}
              {isReal ? (
                <Button type="submit" disabled={add.isPending}>
                  {add.isPending ? "Đang thêm…" : "Thêm vào lớp"}
                </Button>
              ) : (
                <DisabledAction reason={ADD_STUDENT_UNAVAILABLE} variant="default">
                  Thêm vào lớp
                </DisabledAction>
              )}
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
