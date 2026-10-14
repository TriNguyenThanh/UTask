import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useBlocker } from "react-router-dom";

import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { DisabledAction } from "@/features/teacher/components/shared";
import {
  COURSE_CREATE_UNAVAILABLE,
  courseFormSchema,
  emptyCourseForm,
  type CourseFormValues,
} from "@/features/teacher/lib/courseForm";

/**
 * T03. The form is complete and checks everything it can check on its own;
 * creating the class is NOT possible yet because no API for it exists, and
 * the page says so instead of pretending. Nothing is sent or saved.
 */
const CHECK_MESSAGES = {
  idle: "",
  valid: "Thông tin đúng định dạng. Việc tạo lớp vẫn chưa khả dụng.",
  invalid: "Còn thông tin chưa đúng, xem các thông báo cạnh từng ô.",
} as const;

export function Component() {
  const [checked, setChecked] = useState<"idle" | "valid" | "invalid">("idle");
  const form = useForm<CourseFormValues>({
    resolver: zodResolver(courseFormSchema),
    defaultValues: emptyCourseForm,
    mode: "onChange",
  });
  const dirty = form.formState.isDirty;

  // Leaving with edits asks first, whichever way the person leaves.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  );

  // In-app navigation is covered by the blocker; closing the tab or refreshing
  // is not, so the browser's own prompt covers that.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function checkInformation() {
    const valid = await form.trigger();
    setChecked(valid ? "valid" : "invalid");
  }

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
          description="Nhập thông tin lớp. Giao diện kiểm tra định dạng ngay khi bạn nhập."
        />
      </div>

      <Alert className="border-amber-300 bg-amber-50 text-amber-950">
        <AlertTitle>Chưa thể tạo lớp</AlertTitle>
        <AlertDescription>
          {COURSE_CREATE_UNAVAILABLE}
        </AlertDescription>
      </Alert>

      <Form {...form}>
        <form
          noValidate
          aria-label="Thông tin lớp mới"
          className="max-w-2xl space-y-5"
          onSubmit={(event) => event.preventDefault()}
        >
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
            <output className="block text-sm">
              {CHECK_MESSAGES[checked]}
            </output>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => void checkInformation()}>
                Kiểm tra thông tin
              </Button>
              <DisabledAction reason={COURSE_CREATE_UNAVAILABLE} variant="default">
                Tạo lớp
              </DisabledAction>
              <Button asChild variant="ghost">
                <Link to="/teacher/courses">Hủy</Link>
              </Button>
            </div>
          </div>
        </form>
      </Form>

      <Dialog open={blocker.state === "blocked"} onOpenChange={(open) => !open && blocker.reset?.()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rời khỏi trang?</DialogTitle>
            <DialogDescription>
              Thông tin bạn đã nhập chưa được lưu ở đâu cả và sẽ mất nếu rời trang.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => blocker.reset?.()}>
              Ở lại và tiếp tục nhập
            </Button>
            <Button variant="destructive" onClick={() => blocker.proceed?.()}>
              Rời trang
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
