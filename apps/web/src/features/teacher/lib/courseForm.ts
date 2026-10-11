import { z } from "zod";

/**
 * Format checks for the class creation form. The form keeps every field as
 * text (what the inputs hold) and this schema judges it, so the messages sit
 * next to the field that caused them. Bounds that nobody has decided (a
 * maximum team size, subject-code format beyond plain characters) are NOT
 * invented here; the backend owns them.
 */

const COURSE_CODE = /^[A-Za-z0-9._-]+$/;

function wholeNumber(value: string): number | null {
  return /^\d+$/.test(value.trim()) ? Number(value.trim()) : null;
}

export const courseFormSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(3, "Tên lớp cần ít nhất 3 ký tự.")
      .max(120, "Tên lớp tối đa 120 ký tự."),
    courseCode: z
      .string()
      .trim()
      .max(20, "Mã môn tối đa 20 ký tự.")
      .refine((value) => value === "" || COURSE_CODE.test(value), "Mã môn chỉ gồm chữ, số và . _ -"),
    term: z.string().trim().min(3, "Nhập học kỳ, ví dụ HK1 2026–2027."),
    startsOn: z.string().min(1, "Chọn ngày bắt đầu."),
    endsOn: z.string().min(1, "Chọn ngày kết thúc."),
    minMembers: z.string(),
    maxMembers: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.startsOn && values.endsOn && values.endsOn < values.startsOn) {
      ctx.addIssue({
        code: "custom",
        path: ["endsOn"],
        message: "Ngày kết thúc phải sau hoặc cùng ngày bắt đầu.",
      });
    }
    const min = wholeNumber(values.minMembers);
    const max = wholeNumber(values.maxMembers);
    if (min === null || min < 1) {
      ctx.addIssue({
        code: "custom",
        path: ["minMembers"],
        message: "Sĩ số tối thiểu phải là số nguyên từ 1 trở lên.",
      });
    }
    if (max === null || max < 1) {
      ctx.addIssue({
        code: "custom",
        path: ["maxMembers"],
        message: "Sĩ số tối đa phải là số nguyên từ 1 trở lên.",
      });
    }
    if (min !== null && max !== null && min >= 1 && max >= 1 && min > max) {
      ctx.addIssue({
        code: "custom",
        path: ["maxMembers"],
        message: "Sĩ số tối đa phải lớn hơn hoặc bằng sĩ số tối thiểu.",
      });
    }
  });

export type CourseFormValues = z.infer<typeof courseFormSchema>;

export const emptyCourseForm: CourseFormValues = {
  name: "",
  courseCode: "",
  term: "",
  startsOn: "",
  endsOn: "",
  minMembers: "3",
  maxMembers: "5",
};

/** Why the create button is disabled. One place, so the form and tests agree. */
export const COURSE_CREATE_UNAVAILABLE =
  "Tạo lớp chưa khả dụng: chưa có hợp đồng API tạo lớp của Classroom. Thông tin bạn nhập chưa được lưu hay gửi đi.";
