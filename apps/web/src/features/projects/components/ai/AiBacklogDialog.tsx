import { useState, type ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AiProposalDialog } from "@/features/projects/components/ai/AiProposalDialog";
import {
  backlogFormFromProject,
  buildBacklogBody,
  DESCRIPTION_MAX,
  EMPTY_BACKLOG_FORM,
  validateBacklogForm,
  type BacklogFormValues,
} from "@/features/projects/lib/aiBacklogForm";
import { PRIORITY_OPTIONS } from "@/features/projects/lib/issueForm";
import type { AiBacklogItemDto, AiBacklogResultDto } from "@/lib/api/ai/dto";
import { backlogItemToCreateInput, AI_PRIORITY } from "@/lib/api/ai/proposalMapping";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { createTask } from "@/lib/api/work/endpoints";
import { useWorkProjectRecord } from "@/lib/query/workHooks";

const PRIORITY_LABEL = Object.fromEntries(PRIORITY_OPTIONS.map((option) => [option.value, option.label]));

function BacklogItemDetails({ source }: Readonly<{ source: AiBacklogItemDto }>) {
  return (
    <>
      <p className="flex flex-wrap items-center gap-2">
        <span className="rounded border px-1.5 py-0.5 text-[11px] font-semibold">
          {PRIORITY_LABEL[AI_PRIORITY[source.priority]]}
        </span>
        <span>~{Math.round(source.estimate_points)} điểm</span>
      </p>
      {source.description ? <p className="whitespace-pre-wrap">{source.description}</p> : null}
      {source.rationale ? <p className="italic">{source.rationale}</p> : null}
      {source.acceptance_criteria.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-4">
          {source.acceptance_criteria.map((criterion) => (
            <li key={criterion}>{criterion}</li>
          ))}
        </ul>
      ) : null}
      {source.dependencies.length > 0 ? <p>Phụ thuộc: {source.dependencies.join(", ")}</p> : null}
    </>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: Readonly<{ id: string; label: string; error?: string; children: ReactNode }>) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Nút "AI gợi ý backlog" cho Leader: AI đề xuất issue từ mô tả dự án, Accept tạo từng issue vào Product Backlog. */
export function AiBacklogButton({ projectId }: Readonly<{ projectId: string }>) {
  const client = useApiClient();
  const project = useWorkProjectRecord(projectId).data;
  const [edits, setEdits] = useState<Partial<BacklogFormValues>>({});
  // Bản ghi dự án có thể về sau khi mở hộp thoại: giá trị điền sẵn là nền, chỉ phần người dùng sửa mới đè lên.
  const values: BacklogFormValues = { ...(project ? backlogFormFromProject(project) : EMPTY_BACKLOG_FORM), ...edits };
  const errors = validateBacklogForm(values);
  const change = (patch: Partial<BacklogFormValues>) => setEdits((current) => ({ ...current, ...patch }));

  return (
    <AiProposalDialog<AiBacklogResultDto, AiBacklogItemDto>
      triggerLabel="AI gợi ý backlog"
      triggerSize="sm"
      title="AI gợi ý backlog"
      description="AI đọc mô tả dự án và đề xuất các issue. Chỉ những mục bạn chọn mới được tạo trong Product Backlog."
      onOpen={() => setEdits({})}
      canGenerate={Object.keys(errors).length === 0}
      form={
        <>
          <Field id="ai-backlog-description" label="Mô tả dự án" error={errors.description}>
            <Textarea
              id="ai-backlog-description"
              value={values.description}
              maxLength={DESCRIPTION_MAX}
              rows={4}
              onChange={(event) => change({ description: event.target.value })}
            />
          </Field>
          <Field id="ai-backlog-goals" label="Mục tiêu (mỗi dòng một mục)" error={errors.goals}>
            <Textarea id="ai-backlog-goals" value={values.goals} rows={3} onChange={(event) => change({ goals: event.target.value })} />
          </Field>
          <Field id="ai-backlog-tech" label="Công nghệ (mỗi dòng một mục)" error={errors.techStack}>
            <Textarea id="ai-backlog-tech" value={values.techStack} rows={2} onChange={(event) => change({ techStack: event.target.value })} />
          </Field>
          <Field id="ai-backlog-constraints" label="Ràng buộc (mỗi dòng một mục)" error={errors.constraints}>
            <Textarea
              id="ai-backlog-constraints"
              value={values.constraints}
              rows={2}
              onChange={(event) => change({ constraints: event.target.value })}
            />
          </Field>
          <Field id="ai-backlog-extra" label="Hướng dẫn thêm cho AI (tuỳ chọn)">
            <Textarea
              id="ai-backlog-extra"
              value={values.extra}
              maxLength={4000}
              rows={2}
              onChange={(event) => change({ extra: event.target.value })}
            />
          </Field>
        </>
      }
      buildBody={() => buildBacklogBody(projectId, values, project?.end_date ?? null)}
      select={(result) => ({ items: result.items, warnings: result.warnings })}
      renderDetails={(source) => <BacklogItemDetails source={source} />}
      emptyMessage="AI không đề xuất issue nào."
      noun="issue"
      successMessage={(count) => `Đã tạo ${count} issue trong Product Backlog.`}
      create={(source, title, key) => createTask(client, projectId, { ...backlogItemToCreateInput(source, title), idempotencyKey: key })}
    />
  );
}
