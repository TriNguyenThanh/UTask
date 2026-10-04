# Quy tắc cho agent

## Nguồn tài liệu chuẩn

- Bắt đầu từ [tổng quan tài liệu](docs/system/README.md); đọc tài liệu hệ
  thống hoặc service liên quan trước khi thay đổi kiến trúc hay hợp đồng.
- Nội dung kiến trúc chuẩn nằm trong `docs/`. AGENTS chỉ giữ quy tắc làm việc,
  không sao chép tài liệu kiến trúc dài.
- Khi mô tả hiện trạng, kiểm tra mã nguồn, cấu hình, hợp đồng và kiểm thử.
  Dùng nhãn `Đã triển khai`, `Một phần`, `Chưa triển khai`, `Thiết kế mục tiêu`
  hoặc `Chưa xác minh` theo bằng chứng. Không suy luận mã đã triển khai từ
  thiết kế.

## Ranh giới kiến trúc

- Giữ ranh giới service và quyền sở hữu dữ liệu theo
  [kiến trúc hệ thống](docs/system/architecture.md) và
  [quyền sở hữu dữ liệu](docs/system/data-ownership.md).
- Không tạo khóa ngoại xuyên service, không đọc database service khác và không
  tạo service/công nghệ mới nếu chưa có quyết định kiến trúc.
- Dùng REST khi cần phản hồi ngay; dùng Kafka để thông báo sự kiện bất đồng bộ.
  Không biến Kafka thành request-response cho truy vấn đồng bộ.
- AI Service là service nội bộ. API AI nhận ý định người dùng; ngữ cảnh nghiệp
  vụ đi qua Kafka vào dữ liệu đọc riêng. AI không gọi REST hoặc database service
  khác để lấy ngữ cảnh, không sở hữu dữ liệu nghiệp vụ gốc và chỉ đề xuất thay
  đổi.
- Integration Service là service duy nhất gọi GitHub API.
- Progress Service tính chỉ số bằng công thức/quy tắc rõ ràng và không phụ
  thuộc AI.
- Project, Task, Sprint và Comment cùng thuộc Project Service. Classroom
  Service sở hữu Group/GroupMember; Project Service sở hữu Project/
  ProjectMember.

## Tài liệu và hợp đồng

- Tài liệu cho đội phát triển viết bằng tiếng Việt dễ hiểu. Giữ tên kỹ thuật
  cần thiết và giải thích thuật ngữ khó ở lần đầu.
- Không mô tả tính năng, API, sự kiện hoặc luồng mục tiêu như đã chạy. Đặt tài
  liệu chuẩn theo service trong `docs/`; README cạnh app chỉ trỏ tới tài liệu
  đó.
- Khi hành vi thay đổi, cập nhật tài liệu, hợp đồng API/sự kiện và kiểm thử bị
  ảnh hưởng. Không tạo schema giả để lấp đầy `contracts/`.
- Cập nhật link sau khi di chuyển hoặc xóa tài liệu; không giữ hai nguồn chuẩn
  cho cùng một chủ đề.

## Kỹ năng

Chỉ dùng skill phù hợp với công việc; không nạp toàn bộ skill nếu công việc không cần.

- `django-expert`: Django, DRF, ORM, migration, API và kiểm thử Django.
- `supabase-postgres-best-practices`: thiết kế, truy vấn, migration và bảo mật
  PostgreSQL. Áp dụng hướng dẫn PostgreSQL chung, bỏ qua nội dung chỉ dành cho
  dịch vụ Supabase nếu dự án không dùng tính năng đó.
- `vercel-react-best-practices`: hiệu năng React và tải dữ liệu phía client.
  Bỏ qua hướng dẫn Next.js/server khi thay đổi ứng dụng Vite phía client.
- `vercel-composition-patterns`: thiết kế component và cách ghép component trong React.

Không sao chép kiến trúc UTask vào skill. Skill chỉ bổ sung hướng dẫn chuyên
môn có ích cho loại công việc tương ứng.

### Quy tắc kiểm thử áp dụng cho mọi skill

- Sau khi viết hoặc thay đổi một hàm chức năng, phải viết hoặc cập nhật unit
  test tương ứng trong cùng thay đổi; không để test dồn sang milestone sau.
- Unit test phải kiểm tra ít nhất đường đi thành công và các nhánh lỗi/biên có
  ý nghĩa với hàm đó. Nếu hàm chỉ là wiring hoặc adapter không thể unit test
  hợp lý, phải nêu lý do và kiểm tra ở test phù hợp hơn.

## Hoàn tất công việc

- Không báo hoàn tất một hàm chức năng nếu thiếu unit test tương ứng, trừ khi
  đã ghi rõ lý do kỹ thuật và phạm vi kiểm tra thay thế.
Chạy formatter, lint, kiểm thử và build phù hợp với thay đổi trước khi báo hoàn
thành. Với thay đổi tài liệu, kiểm tra link nội bộ, tham chiếu cũ và file rỗng
liên quan. Báo rõ những gì đã kiểm tra và phần chưa xác minh.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **UTask** (162 symbols, 190 relationships, 0 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/UTask/context` | Codebase overview, check index freshness |
| `gitnexus://repo/UTask/clusters` | All functional areas |
| `gitnexus://repo/UTask/processes` | All execution flows |
| `gitnexus://repo/UTask/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
