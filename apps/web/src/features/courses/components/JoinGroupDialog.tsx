import { CodeDialog } from "@/features/courses/components/CodeDialog";
import { useJoinGroup } from "@/lib/query/classroomHooks";

export function JoinGroupDialog() {
  return (
    <CodeDialog
      mutation={useJoinGroup()}
      copy={{
        trigger: "Tham gia nhóm bằng mã",
        title: "Tham gia nhóm bằng mã",
        description: "Nhập mã mời do Trưởng nhóm cung cấp.",
        label: "Mã mời nhóm",
        success: "Bạn đã tham gia nhóm.",
      }}
    />
  );
}
