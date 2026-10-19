# Subagent Codex cho UTask

Subagent là agent được phiên chính giao một phần việc có mục tiêu và phạm vi
rõ ràng. Đây là công cụ phát triển trong repo, tách biệt với agent nghiệp vụ
của AI Service.

**Trạng thái: Đã triển khai cấu hình global trên máy hiện tại.** Cấu hình nằm
trong `~/.codex/`, không được lưu trong repo và áp dụng cho các project Codex
của tài khoản này. Mức tiết kiệm token/thời gian qua nhiều task **Chưa xác minh**.

## Cấu hình

- Cấu hình `~/.codex/config.toml` bật subagent, giới hạn tối đa hai thread con
  mở đồng thời và đặt Luna mức reasoning thấp làm mặc định.
- Mỗi file TOML trong `~/.codex/agents/` định nghĩa một vai trò bằng `name`,
  `description` và `developer_instructions`, kèm `model` và
  `model_reasoning_effort` (độ sâu suy luận) riêng. Model của agent chính
  không bị cấu hình này thay đổi.
- Subagent kế thừa quyền, provider và MCP của phiên chính. Yêu cầu chỉ đọc
  trong vai trò explorer/reviewer là quy tắc hành vi, không phải sandbox riêng.
- Mở phiên Codex mới sau khi cập nhật file global để nạp lại vai trò.

Cấu trúc dựa trên [hướng dẫn subagent chính thức của OpenAI](https://developers.openai.com/codex/subagents)
và [tham chiếu cấu hình](https://developers.openai.com/codex/config-reference/).
Nếu client cũ chưa hỗ trợ custom agent TOML, cập nhật client trước khi dùng.

## Vai trò

| Vai trò | Khi dùng | Phạm vi mặc định |
| --- | --- | --- |
| `utask_explorer` | Định vị code, truy vết luồng, thu thập bằng chứng | Chỉ đọc |
| `utask_backend` | Django/DRF, nghiệp vụ và test backend | Service nghiệp vụ được giao; hiện có `apps/identity-service/` |
| `utask_frontend` | React/Vite, giao diện và test | `apps/web/` |
| `utask_ai` | FastAPI/ADK, pipeline, context tools và test | `apps/ai-service/`; tài liệu AI khi được giao |
| `utask_infra` | Compose, Nginx, CI, Dockerfile và script | File hạ tầng được giao |
| `utask_docs` | Tài liệu tiếng Việt, hợp đồng đã chốt | File được giao trong `docs/` hoặc `contracts/` |
| `utask_reviewer` | Review lỗi, quyền, hồi quy và thiếu test | Chỉ đọc |

Phạm vi trong bảng là gợi ý phân công; danh sách file trong task cụ thể xác
định quyền sửa. Không tạo backend chưa có chỉ vì đã xuất hiện trong baseline.
Các vai trò đọc [AGENTS.md](../../AGENTS.md), tài liệu service và skill phù hợp,
không nạp toàn bộ tài liệu/skill mặc định.

## Model theo độ khó

| Vai trò | Model | Reasoning | Mục đích lựa chọn |
| --- | --- | --- | --- |
| `utask_explorer` | `gpt-6-luna` | `low` | Định vị code và lấy bằng chứng gọn |
| `utask_docs` | `gpt-6-luna` | `low` | Cập nhật tài liệu theo bằng chứng đã chốt |
| `utask_infra` | `gpt-6-luna` | `low` | Cấu hình hạ tầng và CI trong phạm vi nhỏ |
| `utask_reviewer` | `gpt-6-luna` | `medium` | Tìm lỗi/hồi quy độc lập, chỉ đọc |
| `utask_frontend` | `gpt-6.1-sol` | `low` | Triển khai giao diện và kiểm thử |
| `utask_backend` | `gpt-6.1-sol` | `low` | Nghiệp vụ, quyền truy cập và test backend |
| `utask_ai` | `gpt-6.1-sol` | `medium` | Pipeline và ranh giới context cần suy luận thêm |

Đây là lựa chọn theo độ khó, không yêu cầu mỗi vai trò dùng một
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
[hướng dẫn subagent](https://developers.openai.com/codex/subagents).

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
   song song, tối đa hai subagent. Không khởi động bước phụ thuộc trước khi có
   kết quả/contract đã chốt; không chạy nhiều bộ test trên cùng database ghi.
5. Sau khi nhận đủ kết quả, agent chính đọc diff, xử lý khác biệt và chỉ giao
   reviewer khi có rủi ro đáng kể hoặc cần review độc lập. Chạy kiểm tra phù hợp
   cho thay đổi kết hợp; chạy
   GitNexus `detect_changes` trước khi commit nếu task có yêu cầu commit.

Subagent trả báo cáo tiếng Việt gồm file đã sửa hoặc bằng chứng đã đọc, kết
quả đạt được, lệnh kiểm tra và kết quả thực tế, rủi ro cùng phần chưa xác minh.
Agent chính chịu trách nhiệm kết quả cuối. Subagent không tự commit/push/deploy.

## Cách dùng

Mở Codex tại root repo và giao task bằng tên vai trò, ví dụ:

```text
Chỉ spawn subagent nếu có phần việc độc lập đáng để chạy song song. Dùng role
phù hợp và model/reasoning đã cấu hình; tối đa hai subagent, không spawn lồng
nhau. Dùng context mới và bàn giao mục tiêu, file, contract, tiêu chí nghiệm
thu; không gửi lịch sử/source/log dài. Không sửa trùng file. Báo cáo tối đa
250 từ, có file:dòng và kiểm tra thực tế. Agent chính tổng hợp, đọc diff và
chạy kiểm tra tích hợp.
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
spawn thêm agent. Mỗi subagent dùng thêm token, nên giới hạn hai thread là mức
tối đa của project và không yêu cầu mọi task dùng đủ hai vai trò.
