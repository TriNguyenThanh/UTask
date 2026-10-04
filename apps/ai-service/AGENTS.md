# Quy tắc phát triển AI Service

**Trạng thái hiện tại: Chưa triển khai.** Khi audit ngày 2026-10-04, thư mục
này chưa có source code, test, package manifest, Dockerfile hoặc implementation
AI nào được theo dõi trong Git. Không suy ra framework hay endpoint từ tài liệu
thiết kế và cấu hình hạ tầng.

## Vai trò

AI Service là capability hỗ trợ nội bộ: nhận yêu cầu hoặc ý định AI, đọc bản
sao ngữ cảnh tối thiểu và trả về đề xuất có cấu trúc. AI không sở hữu dữ liệu
nghiệp vụ gốc, không tự áp dụng thay đổi nghiệp vụ và không được trở thành
dependency bắt buộc của authentication, classroom/project, task, integration,
progress hoặc notification.

## Công nghệ đã xác minh

- Repository/CI dự kiến service Python và gọi `uv`, Ruff, Pytest.
- CI cũng dự kiến Docker image cho `apps/ai-service/`.
- Chưa xác minh framework HTTP, LLM SDK, agent framework, Kafka client,
  provider, database client, cache, type checker hoặc package manifest.
- Không ghi thêm công nghệ chỉ vì README hay thiết kế mục tiêu có nhắc tới nó.

## Phạm vi và đường dẫn

- Chỉ sửa source, test và cấu hình trong `apps/ai-service/**`.
- Tài liệu AI Service chỉ nằm trong `docs/ai-service/**`.
- Có thể đọc service, contract và hạ tầng khác để hiểu integration context,
  nhưng không sửa chúng trong task này.
- Không tạo `apps/ai-service/docs/`.

## Routing tài liệu và progressive disclosure

Sau khi tuân thủ quy tắc đọc `docs/system/README.md` ở root, đọc
`../../docs/ai-service/README.md` để chọn tài liệu theo task. Không đọc toàn bộ
`docs/ai-service/` mặc định. Chỉ nạp tài liệu bắt buộc và section liên quan;
phần tùy chọn chỉ đọc khi thay đổi thực sự chạm vào nó.

| Task | Đọc bắt buộc | Đọc thêm khi cần |
| --- | --- | --- |
| API/request/response | `../../docs/ai-service/api.md`, phần boundary/request của `architecture.md` | `workflow.md` cho orchestration/output; `erd.md` cho persistence |
| Workflow/agent/tool/prompt | section tương ứng của `workflow.md`, phần boundary của `architecture.md` | `api.md` cho API output; `erd.md` cho lưu trữ |
| Context/Kafka/read model | phần Context flow của `architecture.md`, section Context Tool Pool/Kafka của `workflow.md`, `erd.md` | `api.md` nếu response có context metadata; `code-map.md` để tìm entry point |
| Persistence/projection/migration | `erd.md`, phần Context flow của `architecture.md` | `api.md` nếu schema request/result đổi |
| Provider/model/budget/output | section Budget/Structured Output/Model Strategy của `workflow.md` | `api.md` cho contract; `architecture.md` cho failure boundary |
| Định vị/audit code | `code-map.md` và file source đích | Tài liệu thiết kế liên quan đến kết quả audit |
| Chỉ sửa tài liệu | file đích và link trực tiếp của file đó | Không đọc file dài ngoài phạm vi |

Với file dài, tìm heading trước bằng `rg -n '^#|^##|^###' <file>` rồi chỉ đọc
section cần thiết bằng `sed`. Không đọc `workflow.md` toàn bộ cho một task API
đơn giản; không đọc `erd.md` cho task chỉ sửa prompt; không đọc
`tech-stack.md` nếu không đánh giá hoặc thay đổi stack.

Routing chi tiết và từ khóa chọn section nằm tại
`../../.agents/skills/ai-service-workflow/references/document-routing.md`.

- Kiến trúc và boundary: `../../docs/ai-service/architecture.md`.
- API mục tiêu: `../../docs/ai-service/api.md`.
- Bounded agent workflow: `../../docs/ai-service/workflow.md`.
- Vị trí implementation: `../../docs/ai-service/code-map.md`.
- ERD và persistence: `../../docs/ai-service/erd.md`.
- Thay đổi lớn: `.agent/PLANS.md`.
- Skill workflow: `../../.agents/skills/ai-service-workflow/SKILL.md`.

## Commands

Các lệnh dưới đây là lệnh CI đã được khai báo cho service; hiện chưa chạy
được xác nhận vì project files còn thiếu:

```text
uv sync --all-groups --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
docker build --tag utask/ai-service:local .
```

Chưa có command start development server nào được xác minh. Không tự ghi
`uvicorn`, `fastapi`, `pytest` option hoặc health endpoint như implementation
cho tới khi source/config tương ứng xuất hiện.

## Quy tắc làm việc

1. Đọc `docs/ai-service/architecture.md` và `code-map.md` khi task liên quan
   boundary hoặc cần định vị code; chỉ đọc tài liệu bổ sung khi task yêu cầu.
2. Trước khi tạo helper, utility, service, agent, tool, prompt, schema, model,
   client, adapter hoặc abstraction, search toàn bộ `apps/ai-service/` trước.
   Ưu tiên `reuse → extend → create new`.
3. Giữ transport/API tách khỏi application và workflow; không nhét business
   logic, prompt, parsing, provider config và I/O vào HTTP handler hoặc agent.
4. External LLM call phải có timeout/error handling. Validate output có cấu
   trúc trước khi downstream sử dụng; không dùng substring heuristic để thay
   cho schema khi đã có typed model/JSON schema.
5. Không hard-code secret, API credential, provider key hoặc dữ liệu môi trường.
   Không thêm dependency nếu chưa cần và chưa kiểm tra dependency hiện có.
6. AI chỉ đề xuất. Service sở hữu dữ liệu phải xác thực quyền và áp dụng thay
   đổi; AI không ghi database nghiệp vụ và không tạo foreign key xuyên service.
7. Context nghiệp vụ ưu tiên đi qua contract/event và bản đọc nội bộ. Không
   biến Kafka thành request-response, không đọc database service khác và không
   gọi hàng loạt REST service để dựng context nếu contract không yêu cầu.
8. Giữ kiến trúc bounded agent: ADK Workflow kiểm soát macro-flow, `LlmAgent`
   kiểm soát micro-flow/reasoning. Agent chỉ được thấy Context Tool Pool, không
   biết Kafka, database, cache, topic, offset hoặc consumer group.
9. Context tool phải ở mức domain như task/project/team/progress/development
   context; không expose tool đọc Kafka, query database hoặc thao tác hạ tầng.
   Context Layer phải lọc/tổng hợp dữ liệu cần thiết trước khi đưa cho agent.
10. Mỗi agent/workflow phải có budget giới hạn cho model call, tool call,
    specialist call, output token và timeout. Không cho agent loop vô hạn.
    Specialist chỉ dùng khi use case cần và ưu tiên agent-as-tool.
11. Structured output dùng bởi backend phải qua schema validation. Retry/revise
    khi output không hợp lệ phải có giới hạn; proposal không được tự gây side
    effect lên dữ liệu nghiệp vụ.
12. Test AI phải deterministic khi có thể: dùng fake/mock provider, kiểm tra
   schema và business rule độc lập với production LLM.
13. Mỗi hàm chức năng mới hoặc được thay đổi phải có unit test đi kèm trong cùng
   thay đổi. Test tối thiểu phải bao phủ đường đi thành công và nhánh lỗi/biên
   có ý nghĩa; không đẩy unit test sang milestone sau.
14. Sau mỗi prompt dẫn đến thay đổi code trong `apps/ai-service/**`, phải cập
    nhật [`TASKS.md`](.agent/TASKS.md) trong cùng thay đổi. Chuyển task đã hoàn
    thành vào mục **Đã hoàn thành**, ghi file và kiểm thử liên quan; cập nhật
    mục **Đang thực hiện** hoặc **Sẽ làm** cho phần còn lại. Không ghi một task
    là hoàn thành nếu chưa có bằng chứng từ code và kiểm thử. Prompt chỉ đọc,
    giải thích hoặc chỉ sửa tài liệu không bắt buộc cập nhật task log.

Khi hành vi thay đổi, cập nhật tài liệu/contract/test bị ảnh hưởng trong phạm
vi được phép. Nếu cần sửa service, contract hoặc shared code ngoài scope, dừng
việc sửa và ghi requirement trong báo cáo.

Sau khi source xuất hiện, cập nhật code map theo implementation thực tế.
