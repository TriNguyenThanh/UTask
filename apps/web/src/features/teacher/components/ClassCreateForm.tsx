import { zodResolver } from "@hookform/resolvers/zod";
import { GraduationCap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { applyFieldErrors } from "@/features/auth/formErrors";
import { FormBody, FormFooter, FormSection } from "@/features/teacher/components/ClassFormLayout";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import {
  NEW_COURSE,
  classCreateSchema,
  emptyClassCreateForm,
  type ClassCreateValues,
} from "@/features/teacher/lib/courseForm";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useCourseOptions, useCreateClass, useCreateCourse } from "@/lib/query/teacherClassHooks";

const CLASS_FIELDS = {
  course_id: "courseChoice",
  code: "classCode",
  name: "name",
  term: "term",
  starts_on: "startsOn",
  ends_on: "endsOn",
  group_min_size: "minMembers",
  group_max_size: "maxMembers",
} as const;

const COURSE_FIELDS = { code: "newCourseCode", name: "newCourseName" } as const;

const selectClass =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60";

/**
 * T03 với Classroom thật, nằm trong hộp thoại "Tạo lớp". Classroom có hai thực thể: **môn học** (Course, mã duy
 * nhất, dùng chung) và **lớp học** (ClassSection, thuộc một môn, có học kỳ, ngày và sĩ số nhóm). Form tách hai
 * phần đó: chọn hoặc tạo môn, và thông tin lớp. Hai lệnh dùng hai khóa idempotency riêng; khóa đổi khi người dùng
 * sửa dữ liệu (nội dung đổi thì là ý định mới), giữ nguyên khi chỉ thử lại.
 */
export function ClassCreateForm({
  onCreated,
  onCancel,
  onDirtyChange,
}: Readonly<{
  onCreated: (classId: string) => void;
  onCancel: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}>) {
  const courses = useCourseOptions();
  const createCourse = useCreateCourse();
  const createClass = useCreateClass();
  const [formError, setFormError] = useState<string | null>(null);
  const keys = useRef({ course: newIdempotencyKey(), cls: newIdempotencyKey() });
  // Môn vừa tạo: thử lại sau khi tạo lớp lỗi không tạo môn lần hai.
  const createdCourse = useRef<{ id: string; code: string; name: string } | null>(null);

  const form = useForm<ClassCreateValues>({
    resolver: zodResolver(classCreateSchema),
    defaultValues: emptyClassCreateForm,
    mode: "onChange",
  });
  const choice = useWatch({ control: form.control, name: "courseChoice" });
  const dirty = form.formState.isDirty;
  const chosenCourse = (courses.data ?? []).find((course) => course.id === choice);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    const subscription = form.watch(() => {
      keys.current = { course: newIdempotencyKey(), cls: newIdempotencyKey() };
    });
    return () => subscription.unsubscribe();
  }, [form]);

  async function submit(values: ClassCreateValues) {
    setFormError(null);
    let courseId = values.courseChoice;
    try {
      if (values.courseChoice === NEW_COURSE) {
        const made = createdCourse.current;
        if (made?.code === values.newCourseCode.toUpperCase() && made.name === values.newCourseName) {
          courseId = made.id;
        } else {
          const course = await createCourse.mutateAsync({
            code: values.newCourseCode,
            name: values.newCourseName,
            idempotencyKey: keys.current.course,
          });
          createdCourse.current = { id: course.id, code: course.code, name: course.name };
          courseId = course.id;
        }
      }
    } catch (error) {
      reportFailure(error, COURSE_FIELDS);
      return;
    }
    try {
      const cls = await createClass.mutateAsync({
        courseId,
        code: values.classCode,
        name: values.name,
        term: values.term,
        startsOn: values.startsOn,
        endsOn: values.endsOn,
        groupMinSize: Number(values.minMembers),
        groupMaxSize: Number(values.maxMembers),
        idempotencyKey: keys.current.cls,
      });
      onCreated(cls.id);
    } catch (error) {
      reportFailure(error, CLASS_FIELDS);
    }
  }

  function reportFailure(error: unknown, fields: Record<string, keyof ClassCreateValues>) {
    if (error instanceof ApiError && applyFieldErrors(form, error, fields)) {
      setFormError("Còn thông tin chưa hợp lệ, xem các thông báo cạnh từng ô.");
      return;
    }
    setFormError(classErrorMessage(error));
  }

  const submitting = createCourse.isPending || createClass.isPending;

  return (
    <Form {...form}>
      <form
        noValidate
        aria-label="Thông tin lớp mới"
        className="flex min-h-0 flex-1 flex-col"
        onSubmit={(event) => void form.handleSubmit(submit)(event)}
      >
        <FormBody>
          <FormSection>
            {courses.isError ? (
              <p role="alert" className="text-sm text-destructive">
                Không tải được danh sách môn học.{" "}
                <Button type="button" variant="link" className="h-auto p-0" onClick={() => void courses.refetch()}>
                  Thử lại
                </Button>
              </p>
            ) : null}
            <FormField
              control={form.control}
              name="courseChoice"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Môn học</FormLabel>
                  <FormControl>
                    <select className={selectClass} disabled={courses.isPending} {...field}>
                      <option value="">{courses.isPending ? "Đang tải danh sách môn học…" : "Chọn môn học…"}</option>
                      {(courses.data ?? []).map((course) => (
                        <option key={course.id} value={course.id}>
                          {course.code} — {course.name}
                        </option>
                      ))}
                      <option value={NEW_COURSE}>+ Tạo môn học mới</option>
                    </select>
                  </FormControl>
                  {chosenCourse ? (
                    <FormDescription>
                      Lớp mới thuộc môn {chosenCourse.code} — {chosenCourse.name}.
                    </FormDescription>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            {choice === NEW_COURSE ? (
              <div className="grid items-start gap-4 rounded-lg border border-dashed bg-muted/30 p-4 sm:grid-cols-[1fr_2fr]">
                <FormField
                  control={form.control}
                  name="newCourseCode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Mã môn mới</FormLabel>
                      <FormControl>
                        <Input placeholder="SE330" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="newCourseName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tên môn mới</FormLabel>
                      <FormControl>
                        <Input placeholder="Đồ án Chuyên ngành" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            ) : null}
          </FormSection>

          <FormSection icon={GraduationCap} title="Thông tin lớp học">
            <div className="grid items-start gap-4 sm:grid-cols-[1fr_1fr]">
              <FormField
                control={form.control}
                name="classCode"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Mã lớp</FormLabel>
                    <FormControl>
                      <Input placeholder="SE330.P11" {...field} />
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
                      <Input placeholder="HK1 2026–2027" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tên lớp</FormLabel>
                  <FormControl>
                    <Input placeholder="Ví dụ: Đồ án Chuyên ngành Công nghệ Phần mềm" {...field} />
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
            </div>
            <div className="grid items-start gap-4 sm:grid-cols-2">
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
          </FormSection>

          {formError ? (
            <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {formError}
            </p>
          ) : null}
        </FormBody>

        <FormFooter>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
            Hủy
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Đang tạo lớp…" : "Tạo lớp"}
          </Button>
        </FormFooter>
      </form>
    </Form>
  );
}
