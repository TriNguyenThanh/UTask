import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/features/auth/AuthProvider";
import { RealComments } from "@/features/projects/components/RealCollab";

/**
 * Phản hồi của giảng viên cho dự án của nhóm: bình luận cấp dự án của Work. Server tự gắn huy hiệu
 * phản hồi giảng viên. Bình luận không đổi task, hạn chót hay người được giao.
 */
export function RealTeamFeedback({
  projectId,
  members,
}: Readonly<{ projectId: string; members: readonly { userId: string; name: string }[] }>) {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Phản hồi cho nhóm</CardTitle>
      </CardHeader>
      <CardContent>
        <RealComments
          target={{ projectId }}
          title="Phản hồi"
          actor={{ userId: user.id, isLeader: false, canComment: true, canUpload: false }}
          people={members}
        />
      </CardContent>
    </Card>
  );
}
