# Refactor cấu trúc AI Service theo layer

## Mục tiêu và hiện trạng

**Đã xác minh:** bootstrap có 39 test pass. `api/` và `models/` đã tách theo
trách nhiệm, nhưng application/workflow/provider/repository còn là các module
phẳng. Protocol và adapter nằm chung; application biết workflow cụ thể.

## Phạm vi và cấu trúc

- `api/`: HTTP transport, giữ route/dependency/middleware/handler hiện có.
- `application/`: service điều phối request, dựng response và ports (hợp đồng
  repository/workflow). `StoredRequest` thuộc hợp đồng lưu yêu cầu AI.
- `workflow/`: bounded runtime và hợp đồng `ModelProvider` mà runtime cần.
- `infrastructure/`: adapter provider mặc định và repository in-memory.
- `models/`: giữ schema request/result/response và public imports hiện tại.
- `main.py`: nơi duy nhất lắp ghép implementation cụ thể với HTTP app.

Hướng phụ thuộc: API → application; workflow và infrastructure triển khai các
hợp đồng phía trong. Application/workflow không import infrastructure hay
FastAPI. Không tạo các thư mục agent/tool/context/worker rỗng khi chưa có
implementation. ADK, Celery, provider thật, context và database vẫn là thiết kế
mục tiêu; không thêm dependency cho refactor này.

## Tác động và ràng buộc

GitNexus impact trước sửa báo LOW cho application, workflow, các protocol,
adapter, app factory và helper dựng response/fingerprint. Callers nằm trong
app factory, API dependencies/routes và test; luồng ảnh hưởng là tạo request
→ provider. Giữ nguyên tên symbol; chỉ di chuyển module và cập nhật import.

Giữ route, JSON/schema, status code, timeout, idempotency, ownership và hành
vi provider mặc định. Không thay đổi contract/event hoặc service khác. Source
hiện chưa được Git track; giữ snapshot ngoài repository để so sánh thay đổi
thực tế, không dùng diff tài liệu làm bằng chứng source không ảnh hưởng.

## Các bước

1. Lưu snapshot source và OpenAPI/Pydantic schema, chạy bộ test hiện tại.
2. Tách hợp đồng, adapter, service/response construction và bounded workflow;
   cập nhật app factory và import trong test.
3. Thêm unit test repository, response helpers; giữ test thành công/lỗi
   application/workflow. Kiểm tra dependency giữa layer bằng AST.
4. Cập nhật code map, kiến trúc hiện trạng và task log theo source thực tế.
5. Chạy locked sync, Ruff, Pytest, so sánh schema, Docker build và container
   smoke; kiểm tra link/đường dẫn cũ/file rỗng và GitNexus detect_changes.

## Tiêu chí hoàn thành

Source có đúng trách nhiệm/hướng import trên, test cũ và mới pass, schema không
đổi, image chạy được và tài liệu trỏ đúng module. Wiring/protocol/re-export
không có logic độc lập được kiểm tra bằng API test, adapter test và kiểm tra
dependency thay vì mock nội bộ framework.

## Kết quả thực hiện

**Đã triển khai:** source đã tách theo layer trên. Bộ test có 60 ca pass; Ruff,
locked sync, so sánh schema/AST, Docker build và container smoke đều pass.
GitNexus đã lập lại index; kiểm tra import cycle hoàn chỉnh trả 0 vòng.
`detect_changes` chỉ bao phủ tài liệu tracked vì source chưa được Git track;
phần refactor được đối chiếu snapshot và kiểm thử, không dùng zero affected
processes làm bằng chứng an toàn. Chi tiết validation và công việc tiếp theo
nằm trong [task log](TASKS.md).

## Điều chỉnh ngày 2026-10-07 — Source trực tiếp trong src

Theo yêu cầu người dùng, chuyển `main.py`, `config.py`, `errors.py` và toàn bộ
layer lên trực tiếp `src/`. Giữ phân tách trách nhiệm và protocol; import giữa
layer dùng tên module từ source root. Entry point đổi thành
`main:app --app-dir src`; Dockerfile, test và tài liệu chạy được cập nhật cùng
thay đổi. Export tên class/model bên trong layer vẫn giữ; namespace package
bao ngoài không còn được dùng.

Schema và thân các hàm xử lý được đối chiếu snapshot trước khi di chuyển.
Architecture test kiểm tra source root mới và thêm nhánh từ chối import sai
layer/source thiếu. Các kết quả kiểm tra cụ thể nằm trong task log.
