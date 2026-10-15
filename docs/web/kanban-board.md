# Board và Backlog: kéo thả và di chuyển issue

**Trạng thái tài liệu: Một phần đã triển khai, chỉ trên Demo MSW.** Phần mô tả
hành vi (§2–§6) đã đối chiếu với mã nguồn nhánh `feat/web-kanban-dnd`. Phần "Nhu
cầu gửi Project Service" (§7) là **yêu cầu**, chưa phải hợp đồng. Chưa có
backend nào nhận các thao tác ghi này.

Tài liệu này là nguồn chuẩn cho cách người dùng đổi trạng thái, thứ tự và Sprint
của issue trên tab Bảng công việc (Board) và tab Backlog. Hiện trạng các màn
khác nằm ở [student-flow.md](student-flow.md) và
[teacher-flow.md](teacher-flow.md); kế hoạch tổng thể ở
[frontend-roadmap.md](frontend-roadmap.md) (mảng E).

## 1. Phạm vi và nhãn trạng thái

| Hạng mục | Nhãn | Ghi chú |
| --- | --- | --- |
| Kéo thả thẻ trên Board | **Demo MSW** | Đổi cột; Leader còn sắp thứ tự |
| Kéo thả hàng trên Backlog | **Demo MSW** | Chỉ Leader: đổi Sprint, sắp thứ tự |
| Menu thao tác trên mỗi thẻ/hàng | **Demo MSW** | Cách thay thế cho kéo thả |
| Đánh dấu bị chặn kèm lý do | **Demo MSW** | Cờ trên thẻ, không phải một cột |
| Đổi trạng thái trong chi tiết issue | **Demo MSW** | |
| Bộ lọc lưu trên URL | **Đã triển khai** | Chỉ đọc, không cần backend |
| Tạo, sửa nội dung issue; subtask lưu thật; comment | **Chưa triển khai** | Ngoài phạm vi đợt này |
| Giới hạn WIP, swimlane, kéo nhiều thẻ | **Chưa triển khai** | |
| Cập nhật thời gian thực giữa nhiều người | **Chưa triển khai** | Chỉ có phát hiện xung đột (409) |

**Cờ tính năng.** Các thao tác ghi chỉ bật khi `VITE_ENABLE_MOCKS=true`
([featureFlags.ts](../../apps/web/src/lib/featureFlags.ts)). Với backend thật,
Board và Backlog giữ chế độ chỉ đọc như trước, để không có nút nào giả vờ lưu.
Đây là ngoại lệ có chủ đích cho nguyên tắc "nút ghi chỉ bật khi có hợp đồng" ở
[roadmap §3](frontend-roadmap.md#3-nguyên-tắc-cho-giai-đoạn-tích-hợp): ngoại lệ
này chỉ tồn tại ở lớp mock và phải gỡ khi Project Service có hợp đồng.

## 2. Ai được làm gì

Quyền ở giao diện chỉ phản ánh; nơi quyết định cuối là backend (ở Demo MSW là
handler mock). Nguồn nghiệp vụ: [utask-role-analysis.md](utask-role-analysis.md)
§2.1, US-3.1, US-3.3, US-3.4.

| Vai trò | Board | Backlog |
| --- | --- | --- |
| Leader | Kéo mọi thẻ; đổi cột; sắp thứ tự trong cột | Kéo hàng giữa các Sprint và Product Backlog; sắp thứ tự |
| Member | Chỉ kéo thẻ được giao cho mình; thả vào cột là đổi trạng thái | Không kéo; có menu "bị chặn" ở issue của mình |
| Teacher (xem) | Không kéo, không có menu | Không kéo, không có menu |
| Cờ tắt | Như Teacher | Như Teacher |

Quy tắc nằm ở một chỗ để kiểm thử được:
[moveIntent.ts](../../apps/web/src/features/projects/lib/moveIntent.ts)
(`planMove`, `planReorderToEdge`). Giao diện chỉ gọi hàm này rồi hiển thị kết
quả.

## 3. Quy tắc thứ tự (`rank`)

- Mỗi issue có `rank`: một chuỗi theo kiểu chỉ số phân số (fractional index,
  thư viện `fractional-indexing`). Mọi danh sách (từng cột Board, từng khu
  Backlog) sắp theo `rank`; trùng thì so theo `key`.
- Chuyển một thẻ chỉ ghi một `rank` mới nằm giữa hai thẻ láng giềng đang hiển
  thị, không đánh số lại các thẻ khác.
- Đổi trạng thái không đổi `rank`, nên thẻ tự rơi đúng vị trí ưu tiên ở cột
  mới. Vì vậy một Member đổi cột không cần quyền sắp thứ tự.
- Thả đúng chỗ cũ, hoặc thả lên chính thẻ đang kéo, không gửi gì lên server.

## 4. Đổi phạm vi Sprint đang chạy

Thêm một issue vào Sprint `active`, hoặc đưa nó ra khỏi Sprint `active`, bắt
buộc nhập lý do (US-3.4). Hộp thoại
([ReasonDialog.tsx](../../apps/web/src/features/projects/components/ReasonDialog.tsx))
hiện ra trước khi gọi API; hủy hộp thoại thì không đổi gì. Chuyển giữa Sprint
`upcoming` và Product Backlog không cần lý do. Lý do được ghi vào Lịch sử của
issue. Handler mock cũng từ chối (422) nếu thiếu lý do.

## 5. Cờ bị chặn và quá hạn

- **Bị chặn** (`blocked`, `blockedReason`) là cờ trên thẻ; thẻ giữ nguyên cột.
  Đánh dấu bắt buộc có lý do (US-3.3). Leader đánh dấu được mọi thẻ; Member chỉ
  thẻ của mình.
- **Quá hạn** là suy ra: có `dueAt`, đã qua ngày, và chưa `done`. Issue không
  có `dueAt` không bao giờ bị coi là quá hạn
  ([issueMeta.ts](../../apps/web/src/features/projects/issueMeta.ts)).
- Merge Pull Request **không** tự chuyển thẻ sang Done (US-5.2).

## 6. Trợ năng (accessibility)

- **Cách thay thế cho kéo** (WCAG 2.2, tiêu chí 2.5.7): mỗi thẻ/hàng có nút
  "Thao tác cho `<key>`" mở menu: chuyển sang từng cột, lên đầu/xuống cuối,
  chuyển vào Sprint hoặc về Product Backlog, đánh dấu bị chặn. Menu chỉ liệt kê
  những gì người xem được phép. Tay nắm kéo ẩn với trình đọc màn hình vì đã có
  menu này. Atlassian khuyến nghị dùng menu/nút thay cho phím mũi tên.
- **Thông báo** qua live region
  (`@atlaskit/pragmatic-drag-and-drop-live-region`), ví dụ "NEXUS-101 đã chuyển
  từ Cần làm sang Đang làm" hoặc "… đã chuyển lên vị trí 2".
- **Giữ focus:** sau khi di chuyển, focus quay về nút menu của thẻ đó (kể cả khi
  thẻ được render lại ở cột khác).
- **Thị giác:** vạch báo vị trí dày 2px khi rê qua thẻ (chỉ Leader); cột hoặc khu
  Sprint được tô nền khi thả vào được; thẻ vừa chuyển nhấp nháy 700ms.
- **Chưa kiểm tra:** thao tác kéo thật bằng chuột/cảm ứng và trình đọc màn hình
  (NVDA, Narrator). jsdom không giả lập kéo thả native, nên bản kiểm thử tự
  động chỉ phủ đường menu, quy tắc `planMove` và việc đăng ký phần tử kéo được.

## 7. Nhu cầu gửi Project Service

Đây là yêu cầu của frontend, **không phải schema và không phải hợp đồng**;
không đưa vào `contracts/`. Mock hiện tại (`/api/work/api/v1/...`) bám theo như
sau để chuyển sang thật chỉ phải đổi adapter:

- Issue có thêm `rank` (chuỗi), `version` (số nguyên tăng sau mỗi lần ghi),
  `blocked`, `blockedReason`.
- `POST …/issues/{key}/move` với `{status?, sprintId?, rank?, reason?, version}`.
  Trả issue đã cập nhật. Thiếu quyền → 403; `version` cũ → 409 kèm issue hiện
  tại; Sprint `active` mà thiếu `reason` → 422; Member gửi `rank`/`sprintId` hoặc
  đụng vào issue của người khác → 403.
- `POST …/issues/{key}/blocked` với `{blocked, reason?, version}`; cùng quy tắc
  quyền và `version`; `blocked=true` mà thiếu lý do → 422.
- Mỗi lần ghi thêm một dòng vào Lịch sử (người làm, thời điểm, tóm tắt, lý do).
- Chưa chốt: có nên so `version` toàn thẻ hay chỉ vị trí/cột (để một chỉnh sửa
  không liên quan không chặn một lần kéo); cách xếp thứ tự khi hai người cùng
  chèn vào một chỗ.

## 8. Cách client xử lý ghi

[studentFlowHooks.ts](../../apps/web/src/lib/query/studentFlowHooks.ts):
`useMoveIssue`, `useSetIssueBlocked`.

1. Chỉ ghi cache khi thả (`onMutate`), không ghi trong lúc rê qua các cột, để
   tránh thẻ nhấp nháy.
2. Cập nhật lạc quan nhưng **không** đổi `version`; chỉ câu trả lời của server
   mới được đổi `version` (để lần ghi kế tiếp không bị coi là cũ).
3. Các lần ghi trong cùng project xếp hàng tuần tự (`scope`), `version` được đọc
   lúc yêu cầu thật sự đi ra.
4. Lỗi: trả lại bản chụp cũ, tải lại, hiện thông báo theo mã HTTP (403, 409, 422,
   mất kết nối), không theo nội dung `detail`
   ([moveErrors.ts](../../apps/web/src/features/projects/lib/moveErrors.ts)).

## 9. Bộ lọc trên URL

`q`, `mine`, `pr`, `bug`, `unassigned`, `blocked`, `overdue`, `assignee`,
`priority`, `epic`; dùng chung cho Board và Backlog, và không đụng tới tham số
`issue` (issue đang mở). Làm mới trang hoặc chia sẻ link giữ nguyên bộ lọc.

## 10. Giới hạn đã biết

- Dashboard giảng viên (`teacherFlow`) đọc dữ liệu issue gốc, **chưa** phản ánh
  các thay đổi ghi lúc chạy; chỉ Board/Backlog/chi tiết issue thấy thay đổi.
- Số điểm Sprint trên mock được điều chỉnh theo chênh lệch mỗi lần chuyển vì số
  liệu mẫu được viết tay, không tính lại từ danh sách issue.
- Tab Code và các màn khác chưa dùng `rank`, `blocked`.
- `fractional-indexing` đang ghim bản 3.2.0; bản 4.0.0 đã có, chưa đánh giá.

## 11. Nguồn tham khảo

- Atlassian Design System — Pragmatic drag and drop: hướng dẫn thiết kế, hướng
  dẫn trợ năng, gói hitbox (closest edge).
- W3C WCAG 2.2 — kỹ thuật G219 và lỗi F108 (tiêu chí 2.5.7 Dragging Movements).
- Figma — "Realtime editing of ordered sequences" (chỉ số phân số).
- GitHub Docs — Customizing the board layout (thả vào cột là đổi giá trị trường
  cột; giới hạn WIP là giới hạn mềm).
- Cộng đồng Atlassian (Jira) — thả bị từ chối khi workflow không cho phép; cờ
  "blocked" chỉ là dấu hiệu trên thẻ.
- Discourse — Kanban dùng 409 khi thao tác trên trạng thái đã cũ.
- TanStack Query — mẫu cập nhật lạc quan; thảo luận #9220 về thẻ nhấp nháy.
