import { CodeDialog } from "@/features/courses/components/CodeDialog";
import { useJoinClass } from "@/lib/query/classroomHooks";

export function JoinClassDialog() {
  return (
    <CodeDialog
      mutation={useJoinClass()}
      copy={{
        trigger: "Tham gia lớp bằng mã",
        title: "Tham gia lớp bằng mã",
        description: "Nhập mã tham gia lớp do giảng viên cung cấp.",
        label: "Mã lớp",
        success: "Bạn đã tham gia lớp học.",
      }}
    />
  );
}
