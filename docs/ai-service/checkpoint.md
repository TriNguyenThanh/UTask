# Checkpoint AI Service — 15/10/2026

Đây là bản bàn giao theo source, cấu hình và kiểm thử tại thời điểm checkpoint.
Tài liệu kiến trúc chuẩn vẫn là [architecture](architecture.md), hợp đồng
hành vi là [API v1](api.md), vị trí mã nguồn là [code map](code-map.md).

## Kết quả hiện tại

**Một phần:** AI Service đã chạy local và tạo proposal bằng LLM thật qua
CLIProxyAPI. Ba intent v1 đã được kiểm chứng qua pipeline đầy đủ. Context và
quyền domain local dùng fixture; tích hợp domain thật và production chưa xác minh.

| Phần việc | Trạng thái | Bằng chứng và phạm vi |
| --- | --- | --- |
| FastAPI và schema v1 | Đã triển khai | Health; POST/GET `/api/ai/v1/requests`; schema riêng cho ba intent |
| Xác thực và phân quyền request | Đã triển khai | JWT bất đối xứng, ownership khi polling; worker xác thực/kiểm tra quyền lại |
| Request và hàng đợi bền vững | Đã triển khai | AI PostgreSQL lưu request/delivery; dispatcher giao Redis/Celery, worker claim chống chạy trùng |
| Trả kết quả worker → API | Đã triển khai | Inbox completion, notification và reconcile; API validate rồi ghi trạng thái cuối |
| Giới hạn tiếp nhận | Đã triển khai | Mặc định 5 request mới/phút/user và 2 request active/user; replay không tạo job mới |
| Bounded ADK workflow | Đã triển khai | Giới hạn model/tool/output, deadline 30s, schema validation và revise/retry hữu hạn |
| LLM thật | Đã triển khai local | LiteLLM → endpoint OpenAI-compatible của CLIProxyAPI; model smoke `gemini-3.5-flash-lite` |
| Context Tool Pool | Đã triển khai | Project/task/team/progress/development tools; giữ scope theo target, lọc dữ liệu và kiểm tra freshness |
| Context domain thật | Một phần | REST adapter đã có; hợp đồng/endpoint Work và Integration chưa xác minh; local dùng fixture |
| Áp dụng proposal | Chưa triển khai | AI chỉ trả đề xuất; service sở hữu nghiệp vụ sẽ kiểm tra quyền và áp dụng sau xác nhận |
| Kafka projection, specialist, retention tự động | Chưa triển khai | Không là dependency của pipeline MVP hiện tại |
| Staging/production và chất lượng model | Chưa xác minh | Local smoke chưa chứng minh deployment, quota, chi phí hoặc chất lượng thực tế |

## Pipeline đã chạy

```text
POST request + JWT
  → application kiểm tra quyền và idempotency
  → AI PostgreSQL: queued + delivery
  → dispatcher → Redis → Celery worker
  → xác thực lại → ADK workflow → LlmAgent → Context Tool Pool
  → LiteLLM → CLIProxyAPI → LLM thật
  → validation → completion inbox + notification
  → API tiếp nhận → succeeded/result hoặc failed/error
  → GET request để polling kết quả
```

POST chờ tối đa 10 giây: trả 200 khi hoàn thành, 202 nếu cần polling. API,
dispatcher và worker là các process của cùng AI Service, cùng AI database.
Agent chỉ được dùng domain tools; không gọi HTTP tùy ý, đọc database service
khác hay tự tạo/sửa dữ liệu nghiệp vụ.

## LLM và xử lý lỗi đã hoàn thiện

- Model, base URL và API key đi qua config/provider adapter; không hard-code
  credential. Secret giữ trong `.env` root, không đưa vào prompt hoặc task.
- LiteLLM gửi JSON mode; typed schema vẫn kiểm tra output theo intent.
  Proxy có thể bọc Markdown: workflow chỉ gỡ một JSON fence bao trọn output
  rồi validate, không trích JSON từ văn bản tùy ý.
- Text reasoning có `thought=True` được bỏ khỏi JSON proposal. Output token
  của LiteLLM đã gồm reasoning nên chỉ tính completion usage một lần.
- Tắt retry ẩn ở LiteLLM và SDK OpenAI. Workflow retry lỗi 429/5xx/kết nối/
  timeout provider trong cùng budget/deadline; lỗi cấu hình/quyền provider
  được từ chối. Output sai schema chỉ revise trong giới hạn.
- Model `gemini-3.8-flash-high` từng vượt deadline 30s. Stack local hiện dùng
  override `gemini-3.5-flash-lite`; giữ deadline của hợp đồng API v1.

Source: [provider](../../apps/ai-service/src/infrastructure/providers.py),
[workflow](../../apps/ai-service/src/workflow/bounded.py),
[tools](../../apps/ai-service/src/context/tools.py),
[context adapter](../../apps/ai-service/src/infrastructure/context_http.py).

## Bằng chứng inference thật

Smoke chạy qua API/dispatcher/Redis/Celery/ADK/completion với JWT local ký
thật và context fixture. Kết quả với bản runtime cuối cùng:

| Intent | Kết quả | Thời gian quan sát | Request ID |
| --- | --- | --- | --- |
| task_decomposition | succeeded, 3 subtasks; context task | 13,1s | `368fdcc8-c80d-4349-b889-76cf514698f5` |
| backlog_generation | succeeded, 2 items; context project | 5,3s | `8e0c1d2c-a40a-4364-a49c-07ddd4fb737b` |
| risk_analysis | succeeded, 1 risk; context progress/team/project/github_activity | 4,9s | `cde35f26-5126-467e-92d8-825aaadcf922` |

Số lượng và thời gian là quan sát một lần chạy, không là cam kết hay benchmark.
Schema hợp lệ không thay thế đánh giá chất lượng đề xuất.

## Kiểm thử và cách tiếp tục

Unit tests dùng fake provider hoặc HTTP transport fake; HTTP boundary tests
giữ ADK/LiteLLM/OpenAI thật để kiểm tra JSON mode, tool call ID, reasoning,
retry 503, không retry 401 và timeout. Integration tests dùng PostgreSQL/Redis
test riêng, bao phủ pipeline, completion, idempotency, quota và phân quyền.
Lệnh và kết quả kiểm tra mới nhất ghi tại
[task log](../../apps/ai-service/.agent/TASKS.md).

Kiểm tra cuối: **281 passed, 0 skipped**; Ruff check/format 86 file pass;
Docker build, Compose health và model/base override pass. Ba module liên quan
trên host có credential local: **51 passed**, xác nhận SDK không tự nạp `.env`
vào test process. Kiểm tra link tài liệu và `git diff --check` pass. Còn warning
experimental ADK; không ảnh hưởng kết quả kiểm thử.

GitNexus đã reindex và chạy change analysis trên toàn worktree, nhưng kết quả
mapping symbol/flow cuối còn bất thường và báo CRITICAL; **Chưa xác minh**
verdict graph cho thay đổi cuối. Không dùng kết quả đó để khẳng định blast
radius thấp. Source/tests và review độc lập là bằng chứng trong checkpoint này.

Stack local đang chạy tại `http://127.0.0.1:8000`; JWT owner/outsider đã refresh
tại `.env.mock/`. Từ `apps/ai-service/`, tái khởi động cùng model đã kiểm chứng:

```sh
AI_MODEL=gemini-3.5-flash-lite docker compose --project-name ai-mock \
  --env-file ../../.env --env-file ../../infra/env/ai-service.env \
  up --build -d --wait --wait-timeout 60
```

Request mẫu và cách polling tại [mock data](mock-data.md); cấu hình và lệnh
test/build tại [README](README.md). `MOCK_TEST=true` chỉ thay context/quyền
domain local; LLM vẫn gọi thật. Tắt mock cần endpoint quyền/context đã cấu hình.

## Việc còn lại theo thứ tự

1. Chốt và nối endpoint quyền/context thật của Work/Integration; kiểm tra
   schema, quyền và độ mới dữ liệu. Xác minh issuer/JWKS/public key Identity.
2. Evaluation ba intent trên dữ liệu đại diện; đo tỷ lệ output hợp lệ,
   chất lượng đề xuất, latency, quota và chi phí dưới tải.
3. Xác minh gateway, staging/production, rotation credential, retention và
   vận hành dead-letter. Không suy ra đã deploy từ config/thiết kế.
4. Chỉ thêm Kafka projection hoặc specialist khi có nhu cầu và quyết định
   rõ ràng; chatbot và intent ngoài ba intent v1 còn thuộc phạm vi tiếp theo.
