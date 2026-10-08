# Luồng sinh viên (Student Flow) — hiện trạng triển khai

Tài liệu này mô tả hiện trạng của luồng sinh viên trong `apps/web` sau đợt
tối ưu hóa Student Flow (2026-10). Mỗi mục ghi nhãn theo bằng chứng: **Đã triển
khai** (có mã nguồn + kiểm thử), **Demo MSW** (chạy được với mock, chưa có
backend), **Chưa triển khai** (nút bị vô hiệu hóa hoặc chưa có).

## Điều hướng

- **Đã triển khai**: Task trên Bàn làm việc liên kết
  `/projects/:projectId/board?issue=:key` (TaskRow). Thẻ sprint liên kết Board
  theo `sprint.projectId`; nhóm chưa có workspace thì nút bị vô hiệu hóa kèm
  giải thích (CourseSprintCard). Banner ưu tiên liên kết đến trang thành lập
  nhóm, board sprint hoặc danh sách việc quá hạn (PriorityBanner). Chủ đề đã
  duyệt trong trang nhóm liên kết backlog workspace (CourseTeamRoute).
- **Đã triển khai**: Drawer di động tự đóng khi đổi route (AuthenticatedLayout).

## Dữ liệu & cache

- **Đã triển khai**: API client nhận object, tự stringify một lần; các mutation
  (tạo nhóm, lưu AI key, cập nhật hồ sơ) truyền object thẳng, bỏ double
  `JSON.stringify`. `useCreateTeam` invalidate overview + danh sách project;
  `useDisconnectGitHub` invalidate trạng thái GitHub.

## Mock theo quan hệ membership

- **Demo MSW**: Nguồn chuẩn của mock là graph quan hệ
  `mocks/data/relationships.ts`: ghi lại sinh viên đăng ký môn nào, thuộc
  nhóm nào với vai trò gì (leader/member), yêu cầu tham gia nhóm nào đang
  chờ duyệt, và nhóm nào sở hữu project nào. Mọi quyền tra từ cặp
  (user, tài nguyên): mở course/course detail, project workspace,
  settings (chỉ leader của project đó), thông báo theo project truy cập
  được. Không tài khoản demo nào có "role toàn cục" — cùng một tài khoản
  có thể là leader ở project này, member ở project kia, và truy cập
  settings sẽ được phép ở nơi này, cấm (403) ở nơi khác.
- **Demo MSW**: Tài khoản demo tiêu biểu là sinh viên SV01
  (`student@utask.test` / `demo1234`, Lê Minh Khoa 21020999) — thuộc 4
  lớp với 4 trạng thái khác nhau:

  | Môn học | Trạng thái | Hệ quả khi mở UI |
  |---|---|---|
  | IT3090 | Chưa có nhóm | Trang nhóm hiện "Thành lập Nhóm" |
  | SE330 | Leader Team NEXUS | Workspace NEXUS đủ quyền leader (settings, Tạo Epic, AI ước lượng) |
  | CS402 | Member Team DELI | Workspace DELI ẩn hành động leader; /settings trả 403 |
  | SE331 | Chờ duyệt Team PHOENIX | Trang nhóm hiện trạng thái "chờ duyệt" |

- **Demo MSW**: Hai tài khoản demo còn lại: `leader@utask.test` (leader
  NEXUS ở SE330, member DELI ở CS402) và `member@utask.test` (member DELI
  ở CS402, member NEXUS ở SE330). `database.ts` vẫn lưu trạng thái theo
  user: hồ sơ, nhóm đã tạo, thông báo đã đọc, trạng thái ngắt GitHub, cấu
  hình AI key. Tạo nhóm validate thành viên, hạn chót, tên, sĩ số; lần hai
  trả 409. AI key chỉ lưu provider + keyHint (không lưu key gốc).
- Mock không thay thế backend: service thật vẫn phải tự enforce quyền.
- Giản lược mock (cần biết khi so sánh với backend): NEXUS có 2 leader
  (tài khoản leader và SV01) để cả hai tài khoản đều demo được luồng
  leader; cờ `isMine`/`isMe` trên issue và contributor là fixture tĩnh,
  không suy ra theo người xem.

## Trạng thái hiển thị

- **Đã triển khai**: Task `status === "done"` không lọc vào bucket quá hạn/hôm
  nay (taskFilters). Thẻ sprint guard chia 0, clamp 0–100%, hiển thị "Quá hạn N
  ngày". Footer GitHub theo trạng thái sync thật (connected/disconnected/
  error/loading) (MyWorkPage). Sidebar không còn chấm xanh tĩnh.

## Bật mock & khôi phục phiên

- **Đã triển khai**: MSW bật khi `VITE_ENABLE_MOCKS === "true"` (bất kể dev/
  build); production không đăng ký MSW. Phiên mock lưu refresh token theo key
  riêng của mock.

## Chưa có backend — nút vô hiệu hóa kèm giải thích

- Nộp đề tài, hủy yêu cầu tham gia nhóm, kết thúc sprint: chưa có endpoint.
- Phím tắt toàn cục, tự phân nhóm ngẫu nhiên, OAuth GitHub thật: chưa có.

## Kiểm thử

- `apps/web/src/features/student-flow/StudentFlowRegression.test.tsx` phủ:
  deep link task→board, liên kết thẻ sprint, tạo nhóm persist + 409, body
  JSON không double-stringify, 403/401 ở mock, thông báo/hồ sơ/ngắt GitHub
  theo từng user, AI key không lưu key gốc, task done không quá hạn, scope
  thông báo theo project truy cập được.
- `apps/web/src/features/student-flow/MultiMembershipAccess.test.tsx` phủ 8
  luồng của tài khoản SV01 trong MỘT phiên đăng nhập: Home hiện đủ 4 trạng
  thái membership, deep link workspace NEXUS (leader) và DELI (member), mở
  /settings được ở NEXUS nhưng 403 ở DELI, lật qua lại leader↔member qua
  sidebar không cần đăng nhập lại, mở lớp chưa có nhóm IT3090 ở chế độ
  thành lập nhóm, project ngoài phạm vi trả "Không tìm thấy dự án", và
  Home tổng hợp enrollment + task từ cả hai team.