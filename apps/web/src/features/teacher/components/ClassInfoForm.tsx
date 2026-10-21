import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { UnsavedChangesGuard } from "@/components/feedback/UnsavedChangesGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { applyFieldErrors } from "@/features/auth/formErrors";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import { classEditSchema, type ClassEditValues } from "@/features/teacher/lib/courseForm";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { ClassroomCourseDetail } from "@/lib/api/teacherFlow";
import { usePatchClass } from "@/lib/query/teacherClassHooks";

const FIELDS = {
  name: "name",
  term: "term",
  starts_on: "startsOn",
  ends_on: "endsOn",
  group_min_size: "minMembers",
  group_max_size: "maxMembers",
} as const;

function valuesOf(course: ClassroomCourseDetail): ClassEditValues {
  return {
    name: course.name,
    term: course.term,
    startsOn: course.classroom.startsOn,
    endsOn: course.classroom.endsOn,
    minMembers: String(course.teamSize.min),
    maxMembers: String(course.teamSize.max),
  };
}

/** Sửa thông tin lớp. `version` gửi đi là phiên bản đang hiển thị; xung đột thì tải lại và nạp dữ liệu mới. */
export function ClassInfoForm({
  course,
}: Readonly<{ course: ClassroomCourseDetail }>) {
  const patch = usePatchClass(course.courseId);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ClassEditValues>({
    resolver: zodResolver(classEditSchema),
    defaultValues: valuesOf(course),
    mode: "onChange",
  });

  // Lớp đổi trên server (lưu xong, hoặc tải lại sau xung đột): nạp lại để form khớp.
  // Theo `version`, không theo `course`, để số liệu sinh viên đổi không xóa nội dung đang gõ.
  const { reset } = form;
  const { version } = course.classroom;
  const latest = useRef(course);
  latest.current = course;
  useEffect(() => {
    reset(valuesOf(latest.current));
  }, [version, reset]);

  function submit(values: ClassEditValues) {
    setFormError(null);
    patch.mutate(
      {
        version,
        name: values.name,
        term: values.term,
        startsOn: values.startsOn,
        endsOn: values.endsOn,
        groupMinSize: Number(values.minMembers),
        groupMaxSize: Number(values.maxMembers),
        idempotencyKey: newIdempotencyKey(),
      },
      {
        onSuccess: () => toast.success("Đã cập nhật thông tin lớp."),
        onError: (error) => {
          if (error instanceof ApiError && applyFieldErrors(form, error, FIELDS)) {
            setFormError("Còn thông tin chưa hợp lệ, xem các thông báo cạnh từng ô.");
            return;
          }
          setFormError(classErrorMessage(error));
        },
      },
    );
  }

  return (
    <Card>
      <UnsavedChangesGuard dirty={form.formState.isDirty && !patch.isPending} />
      <CardHeader>
        <CardTitle className="text-base">Thông tin lớp</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            noValidate
            aria-label="Sửa thông tin lớp"
            className="space-y-4"
            onSubmit={(event) => void form.handleSubmit(submit)(event)}
          >
            <p className="text-sm text-muted-foreground">
              Mã lớp <span className="font-mono">{course.classroom.code}</span> và môn{" "}
              <span className="font-mono">{course.courseCode}</span> không đổi được.
            </p>
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tên lớp</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="term"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Học kỳ</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid items-start gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="startsOn"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Ngày bắt đầu</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="endsOn"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Ngày kết thúc</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="minMembers"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sĩ số nhóm tối thiểu</FormLabel>
                    <FormControl>
                      <Input inputMode="numeric" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="maxMembers"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sĩ số nhóm tối đa</FormLabel>
                    <FormControl>
                      <Input inputMode="numeric" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            {formError ? (
              <p role="alert" className="text-sm text-destructive">
                {formError}
              </p>
            ) : null}
            <Button type="submit" disabled={patch.isPending || !form.formState.isDirty}>
              {patch.isPending ? "Đang lưu…" : "Lưu thay đổi"}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
