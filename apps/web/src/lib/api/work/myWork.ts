import { listSemesters } from "@/features/courses/lib/courseList";
import { statusForGroup } from "@/features/projects/issueMeta";
import type { CourseEnrollment, CourseSprint, MyTask, MyWorkOverview, SprintHealth } from "@/features/my-work/types";
import type { ApiClient } from "@/lib/api/client";
import type { WorkProjectCard } from "@/lib/api/work/adapters";
import type { SprintDto, SprintProgressDto, TaskDto } from "@/lib/api/work/dto";
import { getSprintProgress, listSprints, listTasks } from "@/lib/api/work/endpoints";
import { loadProjectCards } from "@/lib/api/work/loaders";

/** Số request song song mỗi đợt, như `loaders.ts`. */
const BATCH = 5;

/** Dự án đầu tiên chưa lưu trữ của mỗi lớp được gắn vào môn tương ứng (để Sidebar mở thẳng dự án). */
export function attachProjects(
  enrollments: readonly CourseEnrollment[],
  cards: readonly WorkProjectCard[],
): CourseEnrollment[] {
  return enrollments.map((enrollment) => {
    const card = cards.find((candidate) => !candidate.archived && candidate.classId === enrollment.courseId);
    return card ? { ...enrollment, projectId: card.projectId } : enrollment;
  });
}

/** `due_date` chỉ có ngày: coi hạn là hết ngày đó (giờ địa phương) để task không "quá hạn" từ 0 giờ. */
function dueAtOf(dueDate: string | null): string | null {
  return dueDate ? `${dueDate}T23:59:00` : null;
}

/** `null` cho SUBTASK: My Work chỉ liệt kê task gốc, như Board. */
export function toMyTask(dto: TaskDto, card: WorkProjectCard): MyTask | null {
  if (dto.type === "SUBTASK") return null;
  return {
    id: dto.id,
    issueKey: dto.code,
    title: dto.title,
    courseId: card.classId ?? "",
    courseCode: card.courseCode,
    projectName: card.name,
    projectId: card.projectId,
    // Web chỉ có ba mức; URGENT gộp vào "high".
    priority: dto.priority === "LOW" ? "low" : dto.priority === "MEDIUM" ? "medium" : "high",
    status: statusForGroup(dto.state?.group ?? "UNSTARTED"),
    dueAt: dueAtOf(dto.due_date),
  };
}

/**
 * Sức khỏe sprint ước lượng từ thời gian đã trôi so với khối lượng đã xong:
 * quá hạn mà chưa xong → trễ; chậm hơn thời gian trôi trên 20 điểm % → rủi ro.
 */
export function sprintHealth(percent: number, startDate: string | null, endDate: string | null, now: Date): SprintHealth {
  if (!endDate) return "on-track";
  const end = new Date(`${endDate}T23:59:59`).getTime();
  if (now.getTime() > end && percent < 100) return "late";
  if (!startDate) return "on-track";
  const start = new Date(`${startDate}T00:00:00`).getTime();
  const span = end - start;
  if (span <= 0) return "on-track";
  const elapsed = Math.min(1, Math.max(0, (now.getTime() - start) / span)) * 100;
  return percent < elapsed - 20 ? "at-risk" : "on-track";
}

export function toCourseSprint(
  sprint: SprintDto,
  progress: SprintProgressDto,
  card: WorkProjectCard,
  enrollment: CourseEnrollment | undefined,
  now: Date,
): CourseSprint {
  const totals = progress.totals;
  const membership = enrollment?.membership;
  const assigned = membership?.status === "assigned" ? membership : null;
  return {
    courseId: card.classId ?? "",
    courseCode: card.courseCode,
    courseName: card.className,
    semester: enrollment?.semester ?? "",
    projectName: card.name,
    projectId: card.projectId,
    teamId: assigned?.teamId ?? card.groupId,
    teamName: assigned?.teamName ?? card.groupName,
    role: assigned ? assigned.role : card.myRole === "LEADER" ? "leader" : "member",
    sprintName: sprint.name,
    completedPoints: totals.completed_estimate_points,
    totalPoints: totals.known_estimate_points,
    deadline: sprint.end_date ? `${sprint.end_date}T23:59:00` : "",
    health: sprintHealth(totals.completion_percent ?? 0, sprint.start_date, sprint.end_date, now),
    // Work không cấp tên giảng viên.
    instructorName: "",
  };
}

export interface ProjectSlice {
  card: WorkProjectCard;
  tasks: TaskDto[];
  sprint: SprintDto | null;
  progress: SprintProgressDto | null;
}

export function buildMyWorkOverview(input: {
  enrollments: readonly CourseEnrollment[];
  /** Mọi dự án của tôi (kể cả đã lưu trữ): dùng để gắn dự án vào môn học. */
  cards: readonly WorkProjectCard[];
  slices: readonly ProjectSlice[];
  partial: boolean;
  now: Date;
}): MyWorkOverview {
  const enrollments = attachProjects(input.enrollments, input.cards);
  const byCourse = new Map(enrollments.map((enrollment) => [enrollment.courseId, enrollment]));
  const tasks = input.slices.flatMap((slice) =>
    slice.tasks.map((dto) => toMyTask(dto, slice.card)).filter((task): task is MyTask => task !== null));
  const sprints = input.slices.flatMap((slice) =>
    slice.sprint && slice.progress
      ? [toCourseSprint(slice.sprint, slice.progress, slice.card, byCourse.get(slice.card.classId ?? ""), input.now)]
      : []);

  const open = tasks.filter((task) => task.status !== "done" && task.dueAt !== null);
  const today = input.now.toDateString();
  const percents = input.slices.flatMap((slice) => (slice.progress ? [slice.progress.totals.completion_percent ?? 0] : []));
  return {
    semester: listSemesters(enrollments)[0] ?? "",
    refreshedAt: input.now.toISOString(),
    enrollments,
    tasks,
    sprints,
    summary: {
      dueToday: open.filter((task) => new Date(task.dueAt ?? "").toDateString() === today).length,
      overdue: open.filter((task) => new Date(task.dueAt ?? "") < input.now).length,
      // Work không có dữ liệu pull request.
      openPullRequests: 0,
      sprintProgressPercent: percents.length === 0 ? 0 : Math.round(percents.reduce((a, b) => a + b, 0) / percents.length),
    },
    partial: input.partial,
  };
}

async function inBatches<T, R>(items: readonly T[], run: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = [];
  for (let start = 0; start < items.length; start += BATCH) {
    results.push(...(await Promise.all(items.slice(start, start + BATCH).map(run))));
  }
  return results;
}

async function loadSlice(client: ApiClient, userId: string, card: WorkProjectCard): Promise<ProjectSlice> {
  const [tasks, sprints] = await Promise.all([
    listTasks(client, card.projectId, { assigneeId: userId }),
    listSprints(client, card.projectId),
  ]);
  const sprint = sprints.find((candidate) => candidate.status === "ACTIVE") ?? null;
  // Tiến độ sprint chỉ là phần phụ: lỗi thì vẫn giữ task của dự án.
  const progress = sprint ? await getSprintProgress(client, sprint.id).catch(() => null) : null;
  return { card, tasks, sprint, progress };
}

/**
 * Work không có API "việc của tôi" xuyên dự án, nên gom bằng cách hỏi từng dự án còn hoạt động mà tôi là
 * thành viên. Một dự án lỗi bị bỏ qua và đánh dấu `partial`, không làm hỏng cả trang.
 */
export async function loadMyWorkOverview(
  client: ApiClient,
  userId: string,
  enrollments: readonly CourseEnrollment[],
  now: Date = new Date(),
): Promise<MyWorkOverview> {
  const { cards, partial } = await loadProjectCards(client, userId);
  const mine = cards.filter((card) => !card.archived && card.myRole !== null);
  const results = await inBatches(mine, (card) =>
    loadSlice(client, userId, card).then((slice): ProjectSlice | null => slice, (): ProjectSlice | null => null));
  const slices = results.filter((slice): slice is ProjectSlice => slice !== null);
  return buildMyWorkOverview({
    enrollments,
    cards,
    slices,
    partial: partial || slices.length < mine.length,
    now,
  });
}
