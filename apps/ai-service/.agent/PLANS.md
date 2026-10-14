# ExecPlan cho thay đổi lớn của AI Service

Chỉ load file này khi thay đổi có nhiều module hoặc ảnh hưởng orchestration,
provider, Kafka context, nhiều workflow, migration hoặc refactor lớn. Bug nhỏ,
prompt nhỏ, một test hoặc schema đơn giản không bắt buộc có plan.

## Goal

Mục tiêu và kết quả người dùng cần đạt.

## Current state

Implementation, contract và test hiện có; ghi rõ phần đã xác minh và phần chưa
triển khai. Không dùng thiết kế mục tiêu để thay thế bằng chứng từ code.

## Constraints

Boundary service, quyền sở hữu dữ liệu, scope file, compatibility, bảo mật và
các quyết định kiến trúc liên quan.

## Affected components

Liệt kê module, entry point, workflow, tool, provider, context store và test bị
ảnh hưởng; link tới `docs/ai-service/code-map.md` nếu có.

## Proposed changes

Mô tả các thay đổi theo layer, hướng dependency và lý do reuse/extend/create.

## Contract impact

API/schema/output thay đổi gì, versioning và validation ra sao. Không tạo schema
giả khi contract chưa được chốt.

## Event/context impact

Event producer/consumer, topic, transform, lưu trữ, độ cũ, replay và idempotency
bị ảnh hưởng thế nào. Không sửa service ngoài scope.

## Implementation steps

Các bước nhỏ, mỗi bước có file đích và điều kiện hoàn thành.

## Test strategy

Unit/API/workflow/integration test, fake provider, fixture deterministic và các
failure case cần kiểm tra.

## Validation

Formatter, lint, typecheck, test, build và kiểm tra contract phù hợp với code
thực tế; ghi rõ lệnh nào chưa thể chạy.

## Risks

Failure isolation, stale context, timeout, invalid output, security và tác động
chéo service.

## Completion criteria

Danh sách tiêu chí đo được để xác nhận plan đã hoàn tất, gồm tài liệu và scope
verification.
