# Subagent Codex cho UTask

Subagent là agent được phiên chính giao một phần việc có mục tiêu và phạm vi
rõ ràng. Đây là công cụ phát triển trong repo, tách biệt với agent nghiệp vụ
của AI Service.

**Trạng thái: Một phần.** Repo đã có model/reasoning theo vai trò và quy tắc
bàn giao context. Cấu hình được kiểm tra bằng Codex CLI local; model/reasoning
được đối chiếu với danh mục CLI. Đã review chính sách context và cấu hình bằng
subagent với context mới qua tool trực tiếp. Việc thực thi Reviewer với model
Sol mới và việc client tự nạp/thực thi toàn bộ custom role,
cũng như mức tiết kiệm token/thời gian thực tế, **Chưa xác minh**.

## Cấu hình

- [Cấu hình project](../../.codex/config.toml) bật subagent và giới hạn tối đa
  ba thread subagent mở đồng thời, không tính agent chính.
- Mỗi file TOML trong `.codex/agents/` định nghĩa một vai trò bằng `name`,
  `description` và `developer_instructions`, kèm `model` và
  `model_reasoning_effort` (độ sâu suy luận) riêng. Model của agent chính đặt
  trong cấu hình project; có thể đổi bằng model picker hoặc CLI.
- Subagent kế thừa quyền, provider và MCP của phiên chính. Yêu cầu chỉ đọc
  trong vai trò explorer/reviewer là quy tắc hành vi, không phải sandbox riêng.
- Cấu hình project chỉ được nạp khi project được Codex đánh dấu tin cậy.
  Mở phiên Codex mới tại root repo sau khi cập nhật cấu hình; không giả định
  phiên đang chạy đã nạp các vai trò mới.

Cấu trúc dựa trên [hướng dẫn subagent chính thức của OpenAI](https://learn.chatgpt.com/docs/agent-configuration/subagents)
và [tham chiếu cấu hình](https://learn.chatgpt.com/docs/config-file/config-reference).
Nếu client cũ chưa hỗ trợ custom agent TOML, cập nhật client trước khi dùng.

## Vai trò

| Vai trò | Khi dùng | Phạm vi mặc định |
| --- | --- | --- |
| [utask_explorer](../../.codex/agents/utask_explorer.toml) | Định vị code, truy vết luồng, thu thập bằng chứng | Chỉ đọc |
| [utask_backend](../../.codex/agents/utask_backend.toml) | Django/DRF, nghiệp vụ và test backend | Service nghiệp vụ được giao; hiện có `apps/identity-service/` |
| [utask_frontend](../../.codex/agents/utask_frontend.toml) | React/Vite, giao diện và test | `apps/web/` |
| [utask_ai](../../.codex/agents/utask_ai.toml) | FastAPI/ADK, pipeline, context tools và test | `apps/ai-service/`; tài liệu AI khi được giao |
| [utask_infra](../../.codex/agents/utask_infra.toml) | Compose, Nginx, CI, Dockerfile và script | File hạ tầng được giao |
| [utask_docs](../../.codex/agents/utask_docs.toml) | Tài liệu tiếng Việt, hợp đồng đã chốt | File được giao trong `docs/` hoặc `contracts/` |
| [utask_reviewer](../../.codex/agents/utask_reviewer.toml) | Review lỗi, quyền, hồi quy và thiếu test | Chỉ đọc |

Phạm vi trong bảng là gợi ý phân công; danh sách file trong task cụ thể xác
định quyền sửa. Không tạo backend chưa có chỉ vì đã xuất hiện trong baseline.
Các vai trò đọc [AGENTS.md](../../AGENTS.md), tài liệu service và skill phù hợp,
không nạp toàn bộ tài liệu/skill mặc định.

## Model theo độ khó

| Vai trò | Model | Reasoning | Mục đích lựa chọn |
| --- | --- | --- | --- |
| Điều phối chính | `gpt-6.1-sol` | `medium` | Phân công, chốt quyết định, tổng hợp và kiểm tra kết quả |
| `utask_explorer` | `gpt-6-luna` | `high` | Task khám phá có câu hỏi và phạm vi rõ ràng |
| `utask_docs` | `gpt-6-luna` | `high` | Cập nhật/tổng hợp tài liệu từ bằng chứng đã xác định |
| `utask_frontend` | `gpt-6.1-sol` | `medium` | Triển khai giao diện và kiểm thử |
| `utask_backend` | `gpt-6.1-sol` | `high` | Nghiệp vụ, quyền truy cập và nhánh lỗi backend |
| `utask_ai` | `gpt-6.1-sol` | `high` | Pipeline, workflow, context boundary và phục hồi lỗi |
| `utask_infra` | `gpt-6.1-sol` | `medium` | Cấu hình hạ tầng, CI và kiểm tra triển khai |
| `utask_reviewer` | `gpt-6.1-sol` | `high` | Review có rủi ro hoặc thay đổi qua nhiều lớp |

Đây là lựa chọn của project theo độ khó, không yêu cầu mỗi vai trò dùng một
model không trùng nhau. Theo yêu cầu của người dùng, không chọn hoặc spawn
model Astra, kể cả khi nâng model hay xử lý model không khả dụng. Cấu hình
hiện chỉ dùng Sol và Luna.
OpenAI khuyến nghị Luna cho task rõ ràng và Sol cho coding phức tạp.
Nguồn: [hướng dẫn chọn model](https://learn.chatgpt.com/docs/models#recommended-models).
Review nhỏ có thể do agent chính xử lý, không phải luôn spawn Reviewer.

Custom role đặt model/reasoning sẽ ưu tiên giá trị trong file của vai trò.
Đổi model phiên chính không tự đổi các role này. Quyền truy cập model phụ
thuộc tài khoản/provider; danh mục CLI không chứng minh mọi model đã gọi
thành công. Nếu model không khả dụng, báo lỗi và chọn model thay thế được
chấp thuận trong task; không âm thầm bỏ qua review hoặc đổi sang model mạnh hơn.

## Context và chi phí

Mỗi subagent giữ context của thread riêng. Agent chính nhận bản tóm tắt thay
vì toàn bộ hoạt động của thread đó. Các agent vẫn dùng chung filesystem, nên
context riêng không ngăn xung đột sửa file.

- **Context mới — mặc định:** dùng cho task độc lập. Bàn giao mục tiêu, file,
  quyết định/contract đã chốt, bằng chứng và tiêu chí kiểm tra; subagent tự đọc
  tài liệu/skill đúng phạm vi. Không gửi toàn bộ source hoặc lịch sử hội thoại.
- **Kế thừa:** dùng khi lịch sử quyết định ảnh hưởng trực tiếp tới task và khó
  tóm tắt chính xác. Kế thừa là cách khởi tạo thread, không phải chia sẻ bộ nhớ
  hội thoại trực tiếp; thay đổi yêu cầu sau đó cần gửi lại cho subagent.
- **Follow-up:** tiếp tục thread cùng task để giữ kết quả điều tra. Task mới
  không liên quan dùng context mới, tránh tích lũy lịch sử không cần thiết.
- **Đầu ra:** ưu tiên báo cáo khoảng 250 từ, kèm file:dòng, file đã sửa, lệnh
  và kết quả kiểm tra, rủi ro và phần chưa xác minh. Không dán log/source dài.

Chọn cách truyền context khi spawn nếu client/tool có hỗ trợ. Trong tool của
phiên thiết lập này, `fork_turns="none"` tạo context mới và nhận model/reasoning
override; `fork_turns="all"` kế thừa lịch sử cùng model/reasoning của parent,
không nhận override. Khi cần model riêng cùng các quyết định trước đó, dùng
`none` và truyền bản tóm tắt. Đây là tham số tool, không phải khóa trong TOML;
không giả định mọi client có cùng giao diện hoặc hỗ trợ cùng lựa chọn.
Nếu client không cho chọn cách fork, vẫn dùng bản bàn giao ngắn nhưng không
khẳng định đã ngăn client sao chép lịch sử.

Nếu tool không có tham số chọn custom role, agent chính đọc file TOML vai trò,
truyền `model`, reasoning và hướng dẫn vai trò/phạm vi vào task với context mới
theo tham số tool thực có. Chỉ đặt tên task là `utask_backend` hoặc tên vai trò
khác không tự nạp file TOML. Nếu tool cũng không hỗ trợ override model, báo
giới hạn này; không khẳng định đã chạy đúng model theo cấu hình.

Tách context giúp giảm nội dung phải giữ ở thread chính; không tăng giới hạn
context của model và không bảo đảm giảm tổng token của cả nhóm. Subagent có
thể tăng tổng token vì mỗi agent có model/tool work riêng. Chạy song song giúp
giảm thời gian khi task độc lập; tránh đọc/điều tra/kiểm thử lặp không cần thiết.
Chỉ nâng reasoning khi độ khó hoặc kết quả kiểm tra yêu cầu; không dùng Max/
Ultra mặc định để tìm cách tiết kiệm token. Xem
[hướng dẫn subagent](https://learn.chatgpt.com/docs/agent-configuration/subagents).

Mức tiết kiệm phải đo trên task tương đương bằng token/usage của cả nhóm và
thời gian hoàn tất, đồng thời giữ chất lượng và kết quả kiểm thử. Repo chưa có
benchmark chứng minh phần trăm tiết kiệm.

## Phân công

1. Agent chính xác định đầu ra và chia phần việc độc lập. Dùng explorer khi
   chưa biết code liên quan; chốt contract trước các bước triển khai phụ thuộc.
2. Mỗi task ghi mục tiêu, file được sửa, file chỉ đọc, phần ngoài phạm vi,
   tiêu chí chấp nhận và kiểm tra cần chạy; chọn context mới/kế thừa theo quy
   tắc trên. Subagent không tự spawn thêm agent.
3. Không cho hai agent sửa cùng file. Agent chính hoặc một người được chỉ định
   quản lý contract, lockfile, task log và cấu hình dùng chung. Với AI Service,
   việc ghi `.agent/TASKS.md` phải được điều phối và nằm trong cùng thay đổi code.
4. Agent triển khai chạy impact trước khi sửa, bổ sung unit test và chạy kiểm
   tra theo [quy tắc repo](../../AGENTS.md). Subagent báo nhu cầu ngoài phạm vi
   về agent chính, không tự mở rộng task. Các phần triển khai độc lập chạy
   song song, tối đa ba subagent. Không khởi động bước phụ thuộc trước khi có
   kết quả/contract đã chốt; không chạy nhiều bộ test trên cùng database ghi.
5. Sau khi nhận đủ kết quả, agent chính đọc diff, xử lý khác biệt và giao reviewer
   kiểm tra kết quả ổn định. Chạy kiểm tra phù hợp cho thay đổi kết hợp; chạy
   GitNexus `detect_changes` trước khi commit nếu task có yêu cầu commit.

Subagent trả báo cáo tiếng Việt gồm file đã sửa hoặc bằng chứng đã đọc, kết
quả đạt được, lệnh kiểm tra và kết quả thực tế, rủi ro cùng phần chưa xác minh.
Agent chính chịu trách nhiệm kết quả cuối. Subagent không tự commit/push/deploy.

## Cách dùng

Mở Codex tại root repo và giao task bằng tên vai trò, ví dụ:

```text
Dùng model theo cấu hình từng vai trò. Mặc định context mới, chỉ truyền bản
bàn giao ngắn và file cần đọc; kế thừa khi cần lịch sử quyết định. Chạy các
phần độc lập song song, tối đa ba subagent, không sửa chồng file. Mỗi subagent
trả tóm tắt kèm bằng chứng và kiểm tra; agent chính tổng hợp và xác minh.
```

```text
Dùng utask_explorer truy vết luồng đăng nhập và xác định test liên quan.
Chỉ đọc, trả bằng chứng file:dòng và rủi ro; chờ kết quả trước khi sửa.
```

```text
Triển khai thay đổi đã chốt bằng subagent: utask_frontend xử lý file giao diện
và test trong apps/web; utask_backend xử lý API và test trong Identity.
Agent chính chốt và quản lý contract, chia danh sách file không chồng nhau.
Chờ cả hai hoàn thành, chạy kiểm tra tích hợp rồi dùng utask_reviewer review.
```

```text
Dùng utask_ai sửa lỗi pipeline theo phạm vi apps/ai-service/AGENTS.md.
Giao rõ file source/test và người cập nhật .agent/TASKS.md; sau khi kiểm tra
xong, dùng utask_reviewer review lỗi và các nhánh kiểm thử còn thiếu.
```

Trong Codex CLI, dùng `/subagents` để xem hoặc chuyển giữa các thread.
Subagent phù hợp khi các phần việc có thể chạy độc lập; task nhỏ không cần
spawn thêm agent. Mỗi subagent dùng thêm token, nên giới hạn ba thread là mức
mặc định của project và không yêu cầu mọi task dùng đủ ba vai trò.
