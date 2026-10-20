import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { myWorkOverviewRequest } from "@/features/my-work/api/myWork";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { loadCourseEnrollments } from "@/lib/api/classroom/loaders";
import { loadMyWorkOverview } from "@/lib/api/work/myWork";
import { isRealService } from "@/lib/config/services";

export const myWorkKeys = {
  all: ["my-work"] as const,
  overview: ["my-work", "overview"] as const,
};

/**
 * Work và Classroom cùng thật: tổng quan dựng từ lớp học (môn) và fan-out theo từng dự án.
 * Chỉ một trong hai thật thì không có đủ nguồn nên giữ MSW.
 */
const useRealOverview = () => isRealService("work") && isRealService("classroom");

export function useMyWorkOverview() {
  const client = useApiClient();
  const { user } = useAuth();
  const real = useRealOverview();
  return useQuery({
    queryKey: real ? [...myWorkKeys.overview, user?.id ?? ""] : myWorkKeys.overview,
    queryFn: async () => {
      if (!real) return myWorkOverviewRequest(client);
      const userId = user?.id ?? "";
      return loadMyWorkOverview(client, userId, await loadCourseEnrollments(client, userId));
    },
  });
}
