import { useState } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AiProposalDialog } from "@/features/projects/components/ai/AiProposalDialog";
import type { AiDecompositionRequest, AiSubtaskDto, AiTaskDecompositionResultDto } from "@/lib/api/ai/dto";
import { subtaskToCreateInput } from "@/lib/api/ai/proposalMapping";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { createSubtask } from "@/lib/api/work/endpoints";

const DESCRIPTION_MAX = 12_000;
const CRITERIA_MAX = 50;

/** Phần nhập của AI: bỏ khóa rỗng vì AI Service từ chối chuỗi rỗng (422). */
export function buildDecompositionBody(
  taskId: string,
  description: string,
  acceptanceCriteria: readonly string[],
  extra: string,
): AiDecompositionRequest {
  const input: AiDecompositionRequest["input"] = {};
  if (description.trim()) input.task_description = description.trim().slice(0, DESCRIPTION_MAX);
  const criteria = acceptanceCriteria.map((line) => line.trim()).filter(Boolean).slice(0, CRITERIA_MAX);
  if (criteria.length > 0) input.acceptance_criteria = criteria;
  if (extra.trim()) input.additional_instruction = extra.trim();
  return { intent: "task_decomposition", target: { type: "task", id: taskId }, input };
}

function SubtaskDetails({ source, isLeader }: Readonly<{ source: AiSubtaskDto; isLeader: boolean }>) {
  return (
    <>
      {source.description ? <p className="whitespace-pre-wrap">{source.description}</p> : null}
      {source.acceptance_criteria.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-4">
          {source.acceptance_criteria.map((criterion) => (
            <li key={criterion}>{criterion}</li>
          ))}
        </ul>
      ) : null}
      {source.dependencies.length > 0 ? <p>Phụ thuộc: {source.dependencies.join(", ")}</p> : null}
      {isLeader ? <p>~{Math.round(source.estimate_points)} điểm</p> : null}
    </>
  );
}

/** Nút "AI tách nhiệm vụ con" trong panel issue: AI gợi ý, người dùng chọn rồi Accept để tạo thật. */
export function AiDecomposeButton({
  taskId,
  description,
  acceptanceCriteria,
  isLeader,
}: Readonly<{ taskId: string; description: string; acceptanceCriteria: readonly string[]; isLeader: boolean }>) {
  const client = useApiClient();
  const [extra, setExtra] = useState("");

  return (
    <AiProposalDialog<AiTaskDecompositionResultDto, AiSubtaskDto>
      triggerLabel="AI tách nhiệm vụ con"
      triggerSize="xs"
      title="AI tách nhiệm vụ con"
      description="AI đọc nhiệm vụ này và đề xuất các nhiệm vụ con. Chỉ những mục bạn chọn mới được tạo."
      onOpen={() => setExtra("")}
      canGenerate
      form={
        <div className="space-y-1.5">
          <Label htmlFor="ai-decompose-extra">Hướng dẫn thêm cho AI (tuỳ chọn)</Label>
          <Textarea
            id="ai-decompose-extra"
            value={extra}
            maxLength={4000}
            rows={4}
            onChange={(event) => setExtra(event.target.value)}
          />
        </div>
      }
      buildBody={() => buildDecompositionBody(taskId, description, acceptanceCriteria, extra)}
      select={(result) => ({ items: result.subtasks, warnings: result.warnings })}
      renderDetails={(source) => <SubtaskDetails source={source} isLeader={isLeader} />}
      reviewNote={
        isLeader ? null : (
          <p className="text-xs text-muted-foreground">
            Nhiệm vụ con sẽ được giao cho bạn; điểm ước lượng do Leader đặt.
          </p>
        )
      }
      emptyMessage="AI không đề xuất nhiệm vụ con nào."
      noun="nhiệm vụ con"
      successMessage={(count) => `Đã tạo ${count} nhiệm vụ con.`}
      create={(source, title, key) =>
        createSubtask(client, taskId, { ...subtaskToCreateInput(source, title, isLeader), idempotencyKey: key })
      }
    />
  );
}
