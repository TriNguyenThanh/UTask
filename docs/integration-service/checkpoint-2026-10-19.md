# Checkpoint Integration Service — 19/10/2026

**Trạng thái: Một phần.** Source M4 hiện có consent GitHub App, credential
được mã hóa, refresh fencing, installation/repository APIs, webhook durable và
Celery jobs. Cấu hình M4 mặc định tắt. Bộ kiểm thử Integration đạt **524**;
kiểm thử hạ tầng đạt **107**; các service backend đạt tổng **2.313** test.
Lint/format, Django check, migration drift, frontend lint/typecheck, build và
smoke Docker local đã đạt trong các lượt kiểm tra tương ứng. Deploy/GitHub thật
**Chưa xác minh**.

## Bằng chứng hiện trạng

- [Foundation](foundation.md): source, cấu hình, phạm vi kiểm chứng và phần
  chưa xác minh.
- [API](api.md): route và wire shape hiện có trong source.
- [Scope và quyền](scope-access.md): ownership và ranh giới Work.
- [ADR-004](../adr/004-integration-github-account-ownership.md): quyết định
  ownership và vòng đời credential.

## Những điểm cần xác minh trước khi kết luận hoàn tất

- Năm lỗi CI cấu hình AI đã sửa: profile AI local được khôi phục, fixture
  staging tách khỏi `.env` local, và cổng PostgreSQL Integration trong metadata
  CI được đặt rõ là `5432`. Kiểm tra Compose/Nginx và toàn bộ test backend đạt.
- Suite frontend đầy đủ vẫn chưa ổn định: một lượt chạy có 3 ca lỗi ở
  KanbanBoard, TeacherSetup và TeacherWorkspace. Các ca này đều có lượt chạy
  lại riêng đạt (TeacherWorkspace: 28 passed), nhưng chưa có nguyên nhân ổn
  định nên chưa kết luận CI toàn repo xanh.
- Cấu hình deployment và vận hành thực tế của GitHub App, key ring, webhook
  secret, Redis, migration gate, worker và Beat.
- OAuth, refresh, revoke, installation callback, webhook delivery và revoke
  từ GitHub thật.

## Bằng chứng kiểm tra checkpoint

- PostgreSQL 16 và Redis tạm dùng cho lượt CI local; container thử nghiệm đã
  được dọn sau khi chạy. Không coi kết quả mock hoặc PostgreSQL là xác minh
  GitHub thật.
- Smoke Docker Integration đã kiểm tra migration gate, health/401, webhook có
  chữ ký, Beat giao job qua Redis, worker cập nhật metadata và delivery trùng.
- Không có thay đổi source frontend trong đợt sửa 5 lỗi CI; cần xử lý riêng sự
  không ổn định của suite frontend trước khi ghi nhận CI toàn repo đạt.

## Ranh giới

Work vẫn sở hữu Project/Task và quyền nghiệp vụ. M4 không thay đổi Work,
Identity, AI, UI, Kafka hay dùng App private key. Không có Project mutation,
AI context hoặc đồng bộ domain; các phần đó **Chưa triển khai**. Snapshot M3
được giữ tại [kế hoạch OAuth lịch sử](plans/2026-10-19-github-identity-oauth.md)
và không mô tả source hiện hành.
