# Cấu hình và triển khai AI Service

**Trạng thái: Hướng dẫn theo implementation hiện tại.** API AI, worker,
dispatcher và beat chạy cùng image, dùng PostgreSQL riêng của AI và Redis làm
broker. AI xác thực access token và session qua Identity; lấy quyền/context
nghiệp vụ đồng bộ qua internal REST của Work; chỉ lấy GitHub context qua
Integration. AI không đọc database service khác. Kafka không nằm trong luồng
lấy context hiện tại.

Tài liệu này là hướng dẫn chuẩn để chỉnh cấu hình và phát hành tích hợp AI.
Nguồn xác nhận cấu hình là `apps/ai-service/src/config.py`, hai Compose root,
các `infra/env/*.env`, source của service nhận request và contract được tham
chiếu bên dưới. “Có source” không đồng nghĩa đã nghiệm thu runtime ở môi trường
đích.

## 1. Luồng và ranh giới service

```text
Browser → Nginx → AI API → PostgreSQL AI
                       ├→ Identity: JWKS + session-status
                       ├→ Work: authorize + project/task/team/progress context
                       └→ Integration: GitHub context (khi được bật)

AI dispatcher → Redis → AI worker → context/model → PostgreSQL AI → AI API
```

- Identity phát JWT RS256, công bố JWKS và xác minh session còn hoạt động.
- Work sở hữu project/task/sprint, quyết định quyền trên target và trả context
  Work. Mỗi request cần cả Bearer actor và service key caller `ai`.
- Integration chỉ tham gia khi bật GitHub context. Integration kiểm tra
  mapping/consent, xin Work quyền `github.read`, rồi gọi GitHub API.
- AI lưu request, kết quả và Bearer tạm trong database AI để worker xác thực
  lại. Redis chỉ nhận UUID request. Bearer bị xóa khi kết quả được bàn giao
  hoặc request vào trạng thái cuối.
- Context được lấy đồng bộ qua HTTP trong lần chạy workflow; chưa có Kafka
  projection hoặc context cache trong AI.

## 2. Nơi đặt cấu hình

Tạo `.env` từ [mẫu root](../../.env.example), nhưng không dùng giá trị mẫu cho
môi trường dùng chung. Root `.env` giữ giá trị triển khai và secret. Các file
`infra/env/ai-service.env`, `work-service.env` và `integration-service.env`
chỉ ánh xạ biến vào process tương ứng; Compose không truyền tự động mọi biến
trong root `.env` vào mọi container. Hai map URL Work mặc định được khai báo
trong `apps/ai-service/src/config.py`, không cần điền trong `.env` khi dùng
DNS Compose `work-service:8000`. File `infra/env/ai-service.env` chỉ chuyển
override URL nếu được đặt; giá trị rỗng được Settings bỏ qua để dùng mặc định.
Override JSON thay toàn bộ map, không ghép từng key với mặc định. Nếu `.env`
cũ chứa hai biến này, bỏ chúng để dùng cấu hình trong code; `{}` là override
rỗng tường minh và sẽ bị từ chối ở staging/production.

Mỗi service API và worker cần cùng cấu hình xác thực/tích hợp của service đó.
Compose hiện dùng chung `env_file` cho các process AI; Work và Integration
dùng file env riêng của chúng. Sau khi đổi `.env` hoặc `infra/env/*.env`, tạo
lại các container liên quan để process nạp cấu hình mới.

### Identity → AI

AI tải `http://identity-service:8000/.well-known/jwks.json` và gửi access token
tới `POST /api/v1/internal/auth/session-status` bằng Bearer cùng
`X-Service-Key`. Cấu hình:

| Nơi cấu hình | Giá trị |
| --- | --- |
| Identity: `IDENTITY_SERVICE_KEYS` | Caller `ai` với key riêng của AI |
| AI: `AI_IDENTITY_BASE_URL` | `http://identity-service:8000` trong Compose nội bộ |
| AI: `AI_IDENTITY_SERVICE_KEY` | Cùng secret với `IDENTITY_SERVICE_KEYS.ai` |
| Identity/AI: issuer và audience | `AI_JWT_ISSUER`/`AI_JWT_AUDIENCE` phải khớp `IDENTITY_JWT_ISSUER`/`IDENTITY_JWT_AUDIENCE` |

Không dùng private PEM trong AI, không đặt URL JWKS riêng và không dùng key
Identity này cho Work hoặc Integration. Lỗi Identity phải làm request bị từ
chối, không được bỏ qua kiểm tra session.

### AI ↔ Work

Work hiện có các endpoint internal trong
[contract Work AI context v1](../../contracts/api/work-ai-context-v1.yaml):

- `POST /api/v1/internal/ai/targets/{target_type}/{target_id}/authorize`
  với body `{"action":"ai.analyze","intent":"..."}`;
- `GET /api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/{domain}`.

Work luôn yêu cầu Bearer actor và `X-Service-Key` caller `ai`. Đặt cấu hình
ghép cặp sau; để `AI_WORK_SERVICE_AUTH_ENABLED=false` sẽ khiến AI không gửi
header mà Work bắt buộc, nên tích hợp thật phải bật cờ này:

| Nơi cấu hình | Giá trị |
| --- | --- |
| AI: `AI_WORK_SERVICE_AUTH_ENABLED` | `true` |
| AI: `AI_WORK_SERVICE_KEY` | Secret riêng AI→Work |
| Work: `WORK_SERVICE_KEYS` | `ai: [<cùng secret>]`; không dùng chung key Integration |
| AI: `authorization_urls` trong `config.py` | Mặc định đủ `project`, `task`, `sprint`; `AI_AUTHORIZATION_URLS` chỉ cần khi ghi đè địa chỉ |
| AI: `context_urls` trong `config.py` | Mặc định đủ 10 cặp Work; `AI_CONTEXT_URLS` chỉ cần khi ghi đè địa chỉ hoặc thêm GitHub |

URL nội bộ mặc định dùng DNS Compose, ví dụ
`http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize`.
Các context URL dùng cùng base/path rồi domain cố định ở cuối. Chỉ dùng
placeholder `{target_type}` và `{target_id}`. Danh sách đầy đủ các 3 authorize
map và 10 context map, cùng schema/ma trận intent-target, nằm trong
[hướng dẫn provider Work–AI](../project-service/ai-service-integration-guide.md#6-cấu-hình-phối-hợp-với-ai-và-integration).

Work kiểm tra quyền actor và target mỗi lần authorize/context; kết quả
authorize trước đó không thay thế lần kiểm tra khi đọc context. AI không gửi
`actor_id` để Work tin cậy và không gọi database Work trực tiếp.

### AI → Integration (chỉ khi bật GitHub context)

Mặc định GitHub context tắt. Để bật cần hoàn tất đồng thời:

| Nơi cấu hình | Giá trị |
| --- | --- |
| AI: `AI_GITHUB_CONTEXT_ENABLED` | `true` |
| AI: `AI_INTEGRATION_SERVICE_KEY` | Khớp caller `ai` trong `INTEGRATION_SERVICE_KEYS` |
| AI: `AI_CONTEXT_URLS` | Thêm `project:github_activity` trỏ tới `http://integration-service:8000/api/v1/internal/projects/{target_id}/github/context` |
| Integration: `INTEGRATION_AI_CONTEXT_ENABLED` | `true` |
| Integration: `INTEGRATION_CONNECTIONS_ENABLED` | `true`, cùng GitHub App credential/configuration hợp lệ |
| Integration: `INTEGRATION_SERVICE_KEYS` | Caller `ai` nhận đúng secret AI→Integration; caller `work` nhận key Integration→Work |
| Integration: `INTEGRATION_WORK_SERVICE_KEY` | Khớp key caller `integration` trong `WORK_SERVICE_KEYS` |
| Work: `WORK_SERVICE_KEYS` | Có key riêng cho caller `integration`; không trùng key caller `ai` |
| Work: `WORK_GITHUB_CONNECTION_ENABLED` | Bật nếu cần luồng kết nối repository thuộc Work |

Integration gửi tiếp Bearer actor sang Work để kiểm tra `github.read`; không
dùng AI key cho request đó. Integration là service duy nhất gọi GitHub API.
URL trên là ví dụ cho network Compose nội bộ; nếu môi trường dùng host/port/TLS
khác, cấu hình URL nội bộ theo network thực tế. Không dùng gateway prefix cho
endpoint internal.

Chi tiết `ContextDocument`, giới hạn dữ liệu và rollout xem
[hướng dẫn GitHub AI–Integration](../integration-service/ai-service-integration-guide.md).

## 3. Kiểm tra cấu hình trước khi khởi động

Với `AI_ENVIRONMENT=staging` hoặc `production`, `MOCK_TEST` phải là `false`.
Settings AI từ chối khởi động khi thiếu issuer, audience, `AI_IDENTITY_SERVICE_KEY`,
ba authorization URL hoặc một trong 10 Work context URL. Nếu bật Work service
auth, `AI_WORK_SERVICE_KEY` cũng bắt buộc. Nếu bật GitHub context, URL
`project:github_activity` và `AI_INTEGRATION_SERVICE_KEY` bắt buộc.

Kiểm tra các cặp secret trước khi chạy:

| Caller | Secret gửi | Secret nhận |
| --- | --- | --- |
| AI→Identity | `AI_IDENTITY_SERVICE_KEY` | `IDENTITY_SERVICE_KEYS.ai` |
| AI→Work | `AI_WORK_SERVICE_KEY` | `WORK_SERVICE_KEYS.ai` |
| AI→Integration | `AI_INTEGRATION_SERVICE_KEY` | `INTEGRATION_SERVICE_KEYS.ai` |
| Integration→Work | `INTEGRATION_WORK_SERVICE_KEY` | `WORK_SERVICE_KEYS.integration` |
| Work→Integration callback | `WORK_INTEGRATION_SERVICE_KEY` | `INTEGRATION_SERVICE_KEYS.work` |

Các secret phải riêng theo chiều/caller, không commit vào Git và không ghi ra
log. Work key hiện chấp nhận 1–2 key ASCII in được cho xoay vòng; không để
caller AI và Integration dùng chung key. Cấu hình Integration/GitHub chỉ cần
khi bật tính năng GitHub.

## 4. Khởi động và triển khai

### Local

Từ repository root, cấu hình `.env` và các file `infra/env` theo bảng trên,
rồi bật profile cần dùng. Ví dụ chỉ có AI với Work và Identity:

```sh
docker compose --profile identity-service --profile ai-service up --build -d --wait
```

Nếu dùng GitHub context, thêm `--profile integration-service`; cấu hình
Integration/GitHub trước khi bật `AI_GITHUB_CONTEXT_ENABLED`. PostgreSQL và
Redis dùng trong stack phải healthy. Migration AI chạy ở entrypoint API trước
Uvicorn; worker, dispatcher và beat dùng cùng image/configuration và đợi API
healthy. Không có container migration AI riêng.

### Staging

Đặt secret và URL trong `.env` của máy staging, kiểm tra các file env được
Compose tham chiếu, rồi phát hành image qua quy trình CI/CD hiện hành. Chọn
profile `ai-service`; chọn thêm `work-service`, `identity-service` và
`integration-service` nếu chúng chưa chạy hoặc nếu bật GitHub. Staging phải
dùng `MOCK_TEST=false`; không dùng proxy LLM local. Không xóa volume để áp
dụng cấu hình mới hoặc để chuyển database.

Sau khi cập nhật cấu hình, recreate toàn bộ process nhận biến đã đổi. Với key
AI→Work cần recreate AI API/worker/dispatcher/beat và Work API. Với key
AI→Integration cần recreate các process AI và Integration API. Xác nhận rollout
theo service health trước; health chỉ xác nhận process, không xác nhận quyền
domain hoặc LLM thật.

## 5. Xác minh tích hợp và trạng thái bằng chứng

Triển khai cấu hình xong cần kiểm tra theo thứ tự:

1. Identity trả JWKS nội bộ; session-status xác nhận token hợp lệ/đã thu hồi
   tương ứng và từ chối caller key sai.
2. Work authorize cho phép actor có quyền trên target, từ chối actor không có
   quyền; Work context trả đúng domain và từ chối target/domain sai. Gọi thiếu
   một trong hai header phải bị từ chối.
3. Nếu bật GitHub, Integration phải từ chối key AI sai, kiểm tra consent/mapping
   và Work permission, rồi trả `github_activity` theo contract.
4. Gửi request qua AI API và theo dõi trạng thái tới khi worker trả kết quả;
   xác nhận context source dự kiến và không có token/key trong log.

AI, Identity, Work và Integration đều có source/config/test cho các phần được
mô tả; đây là xác minh tĩnh/source/test. Tích hợp runtime thật của một môi
trường chỉ được coi là **Đã xác minh** khi chạy các bước trên với service thật,
key thật được inject an toàn và user/target có quyền phù hợp. Xem biên bản
[Work–AI staging](../project-service/ai-context-staging-validation-20261022.md)
để biết phạm vi smoke đã chạy và phần chưa nghiệm thu. Không suy ra E2E hoàn
chỉnh từ Compose render, healthcheck hoặc test dùng HTTP fake.

## 6. Khi chỉnh sửa contract hoặc cấu hình

1. Xác định service sở hữu endpoint và dữ liệu; giữ API đồng bộ cho context
   cần phản hồi trong cùng workflow.
2. Nếu path, header, request/response hoặc mã lỗi đổi, cập nhật contract trước
   hoặc cùng thay đổi với consumer, provider và contract test.
3. Nếu chỉ đổi host/port, cập nhật URL map cho đúng môi trường; giữ schema và
   placeholder AI hỗ trợ. Không đưa URL tùy ý vào prompt/agent.
4. Nếu đổi caller key, cập nhật cả phía gửi và nhận trong cùng rollout; dùng
   key riêng, recreate process liên quan, rồi xoay/xóa key cũ sau khi xác minh.
5. Cập nhật tài liệu service sở hữu endpoint và bảng này; ghi rõ **Đã triển khai**,
   **Một phần**, **Chưa triển khai**, **Thiết kế mục tiêu** hoặc **Chưa xác minh**
   theo source, contract, test và runtime evidence.

Không đổi việc lấy context sang Kafka request-response. Chỉ xem xét sự kiện
Kafka khi cần thông báo bất đồng bộ hoặc projection có use case, owner và
contract riêng.
