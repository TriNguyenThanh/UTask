import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { applyFieldErrors } from "@/features/auth/formErrors";
import { UnsavedChangesGuard } from "@/features/teacher/components/UnsavedChangesGuard";
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
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

/**
 * T03 với Classroom thật: chọn môn có sẵn hoặc tạo môn mới, rồi tạo lớp. Hai
 * lệnh dùng hai khóa idempotency riêng; khóa đổi khi người dùng sửa dữ liệu
 * (nội dung đổi thì là ý định mới), giữ nguyên khi chỉ thử lại.
 */
export function ClassCreateForm() {
  const navigate = useNavigate();
  const courses = useCourseOptions();
  const createCourse = useCreateCourse();
  const createClass = useCreateClass();
  const [formError, setFormError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const keys = useRef({ course: newIdempotencyKey(), cls: newIdempotencyKey() });
  // Môn vừa tạo: thử lại sau khi tạo lớp lỗi không tạo môn lần hai.
  const createdCourse = useRef<{ id: string; code: string; name: string } | null>(null);

  const form = useForm<ClassCreateValues>({
    resolver: zodResolver(classCreateSchema),
    defaultValues: emptyClassCreateForm,
    mode: "onChange",
  });
  const choice = useWatch({ control: form.control, name: "courseChoice" });
  const dirty = form.formState.isDirty && createdId === null;

  useEffect(() => {
    if (createdId) void navigate(`/teacher/courses/${createdId}`);
  }, [createdId, navigate]);

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
      setCreatedId(cls.id);
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

  if (courses.isPending) {
    return <PageSkeleton label="Đang tải danh sách môn học" />;
  }

  const submitting = createCourse.isPending || createClass.isPending;

  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="space-y-3">
        <Breadcrumbs
          items={[
            { label: "Trang chủ", to: "/teacher" },
            { label: "Lớp phụ trách", to: "/teacher/courses" },
            { label: "Tạo lớp" },
          ]}
        />
        <PageHeader
          title="Tạo lớp"
          description="Chọn môn học, nhập thông tin lớp. Bạn sẽ là giảng viên phụ trách chính của lớp."
        />
      </div>

      {courses.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            Không tải được danh sách môn học.{" "}
            <Button type="button" variant="link" className="h-auto p-0" onClick={() => void courses.refetch()}>
              Thử lại
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form
          noValidate
          aria-label="Thông tin lớp mới"
          className="max-w-2xl space-y-5"
          onSubmit={(event) => void form.handleSubmit(submit)(event)}
        >
          <FormField
            control={form.control}
            name="courseChoice"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Môn học</FormLabel>
                <FormControl>
                  <select className={selectClass} {...field}>
                    <option value="">Chọn môn học…</option>
                    {(courses.data ?? []).map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.code} — {course.name}
                      </option>
                    ))}
                    <option value={NEW_COURSE}>+ Tạo môn học mới</option>
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {choice === NEW_COURSE ? (
            <div className="grid items-start gap-5 sm:grid-cols-2">
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
          <div className="grid items-start gap-5 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="classCode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mã lớp</FormLabel>
                  <FormControl>
                    <Input placeholder="SE330.P11" {...field} />
                  </FormControl>
                  <FormDescription>Mã lớp không trùng với lớp khác.</FormDescription>
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
          <div className="grid items-start gap-5 sm:grid-cols-2">
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
          <div className="grid items-start gap-5 sm:grid-cols-2">
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

          <div className="space-y-3 border-t pt-5">
            {formError ? (
              <p role="alert" className="text-sm text-destructive">
                {formError}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={submitting}>
                {submitting ? "Đang tạo lớp…" : "Tạo lớp"}
              </Button>
              <Button asChild variant="ghost">
                <Link to="/teacher/courses">Hủy</Link>
              </Button>
            </div>
          </div>
        </form>
      </Form>

      <UnsavedChangesGuard dirty={dirty} />
    </div>
  );
}
