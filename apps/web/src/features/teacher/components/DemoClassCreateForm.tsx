import { zodResolver } from "@hookform/resolvers/zod";
import { GraduationCap } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { FormBody, FormFooter, FormSection } from "@/features/teacher/components/ClassFormLayout";
import { DisabledAction } from "@/components/feedback/DisabledAction";
import {
  COURSE_CREATE_UNAVAILABLE,
  courseFormSchema,
  emptyCourseForm,
  type CourseFormValues,
} from "@/features/teacher/lib/courseForm";

const CHECK_MESSAGES = {
  idle: "",
  valid: "Thông tin đúng định dạng. Việc tạo lớp vẫn chưa khả dụng.",
  invalid: "Còn thông tin chưa đúng, xem các thông báo cạnh từng ô.",
} as const;

/**
 * T03 ở chế độ demo (Classroom chưa là dịch vụ thật): kiểm tra mọi định dạng nhưng không có API để tạo lớp,
 * nên nút "Tạo lớp" tắt và hộp thoại nói rõ. Không gửi hay lưu gì.
 */
export function DemoClassCreateForm({
  onCancel,
  onDirtyChange,
}: Readonly<{ onCancel: () => void; onDirtyChange?: (dirty: boolean) => void }>) {
  const [checked, setChecked] = useState<"idle" | "valid" | "invalid">("idle");
  const form = useForm<CourseFormValues>({
    resolver: zodResolver(courseFormSchema),
    defaultValues: emptyCourseForm,
    mode: "onChange",
  });
  const dirty = form.formState.isDirty;

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  async function checkInformation() {
    const valid = await form.trigger();
    setChecked(valid ? "valid" : "invalid");
  }

  return (
    <Form {...form}>
      <form
        noValidate
        aria-label="Thông tin lớp mới"
        className="flex min-h-0 flex-1 flex-col"
        onSubmit={(event) => event.preventDefault()}
      >
        <FormBody>
          <Alert className="border-amber-300 bg-amber-50 text-amber-950">
            <AlertTitle>Chưa thể tạo lớp</AlertTitle>
            <AlertDescription>{COURSE_CREATE_UNAVAILABLE}</AlertDescription>
          </Alert>

          <FormSection>
            <FormField
              control={form.control}
              name="courseCode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mã môn (không bắt buộc)</FormLabel>
                  <FormControl>
                    <Input placeholder="SE330" {...field} />
                  </FormControl>
                  <FormDescription>Nhiều lớp có thể cùng mã môn.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </FormSection>

          <FormSection icon={GraduationCap} title="Thông tin lớp học">
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
          <output className="block text-sm">{CHECK_MESSAGES[checked]}</output>
        </FormBody>

        <FormFooter>
          <Button type="button" variant="ghost" onClick={onCancel}>
            Hủy
          </Button>
          <Button type="button" variant="outline" onClick={() => void checkInformation()}>
            Kiểm tra thông tin
          </Button>
          <DisabledAction reason={COURSE_CREATE_UNAVAILABLE} variant="default">
            Tạo lớp
          </DisabledAction>
        </FormFooter>
      </form>
    </Form>
  );
}
