# Kiểm chứng Work–AI qua HTTP thật trên staging local — 22/10/2026

**Cập nhật sau lượt smoke:** người dùng yêu cầu bỏ hạn chế HTTP LLM theo môi
trường. Source AI đã bỏ đúng điều kiện đó, giữ validation URL/key và budget;
HTTP/HTTPS được kiểm cho cả development/test/staging/production, nhóm test
provider/workflow đạt 74 ca. Các phần dưới ghi snapshot **trước bản sửa này**,
bao gồm blocker `AI_LLM_API_BASE_INVALID` và việc tạm đổi development; không
coi đó là chính sách HTTP hiện tại. [Hành vi mới](../ai-service/README.md).
Đã build/recreate bốn process AI staging local bằng image sửa; giữ `staging`,
`MOCK_TEST=false` và service key bật. Model dựng được, gọi HTTP `/models` 200.
Đây là kiểm chứng đã bỏ chặn cấu hình HTTP, không phải chạy lại các workflow
hoặc chứng minh timeout trong bảng dưới đã được xử lý.

## Kết luận

**Đã kiểm chứng** provider Work với AI, Identity và Classroom thật: quyền,
session và 10 cặp context hoạt động trên các ca đã chạy. **Một phần** đối với
phân tích AI: một ca Task đi hết API → queue → worker → Work → LLM → kết quả;
ba ca khác hết budget 30 giây. Chưa đủ bằng chứng nghiệm thu mọi intent hoặc
độ ổn định dài hạn.

Phải phân biệt hai cấu hình đã kiểm:

- **Staging local:** Compose staging, `.env.staging` thật, volume hiện hữu,
  `MOCK_TEST=false`, JWT/session/service key thật. Deploy đạt; quyền/context đạt.
- **Smoke LLM HTTP local:** chỉ bốn process AI tạm đặt `AI_ENVIRONMENT=development`
  để dùng endpoint HTTP đã cấu hình. Vẫn tắt mock, dùng cùng DB, queue, credential,
  model và service thật. Sau kiểm tra đã recreate về **staging**. Không gọi lượt
  này là LLM chạy thành công dưới chính sách cấu hình staging nguyên trạng.

## Source và môi trường

Tiếp tục đúng stack của [phiên kiểm HTTP trước](../infrastructure/staging-http-validation-20261021.md):
project Docker `utask-staging-local-20261021`, gateway `http://127.0.0.1:18080`.
Không SSH/VPS, không GHCR, không tạo lại volume hoặc reset database.

Đã fetch và fast-forward `dev` đến **`3f6801460c3f`**. Chín file trùng thay đổi
local được sao lưu và ghép ba chiều; các file local ngoài vùng trùng giữ nguyên
từng byte tại thời điểm cập nhật, index trống. Bản sao khôi phục còn trong stash
`72a49fa1bf95`; không pop stash hỗn hợp. Không tạo commit nghiệp vụ.

Work image được build từ worktree có provider chưa commit; AI image build từ
source AI mới trên dev, không sửa code AI để chạy smoke. Các process pin digest:

| Image | Digest |
| --- | --- |
| Work | `sha256:a87de5f37a3144d5e3879ff84d3ede1ec67efed05541722f2df156520a92561b` |
| AI | `sha256:f8f46f1b606713bb316b2e69e456d8b1d81db2cfee3c6b70f91b71a034911487` |

Build/push registry local và nguyên [script deploy](../../scripts/deploy_staging.sh)
đã chạy với profile hiện hữu; deploy Work và lượt có AI đều **exit 0**. Lượt
đầu của probe Windows bị CRLF ở stdin, chưa triển khai; đã truyền binary stdin
đúng và chạy lại, không sửa script để bỏ validation.

Sau pull, cấu hình bổ sung đúng hai điểm trong `.env.staging`: đăng ký key
`AI_IDENTITY_SERVICE_KEY` đã có vào entry `ai` của `IDENTITY_SERVICE_KEYS`, và
đặt `AI_WORK_SERVICE_AUTH_ENABLED=true`. Giữ key `work/classroom` và credential
khác. Đã recreate process nhận env. Cờ phía AI chỉ điều khiển gửi key; Work
vẫn yêu cầu hai header theo [service permission](../../apps/work-service/common/service_permissions.py).

## Kết quả HTTP và runtime

| Kiểm tra | Kết quả thực thi |
| --- | --- |
| Login và Project | Leader/Member/Teacher login 200, đọc Project 200; outsider login 200 nhưng đọc Project 404. |
| Provider Work nội bộ | **60/60 quan sát đúng kỳ vọng**: đủ 10 cặp context với Leader/Member/Teacher, outsider bị 404; thiếu key 403, thiếu actor 401, sai caller 403; authorize `github.read` đúng/sai caller. Context là raw JSON, không quá 65536 byte, mảng không quá 100, no-store. |
| Adapter AI thật | **24 kiểm tra đạt**: xác thực Identity thật rồi đọc 10 cặp cho Member và Teacher; ba target outsider bị từ chối; JWT session thu hồi bị 401. `InternalContextAdapter`, không fixture context. Teacher dùng `RemoteClassroom`. |
| Thu hồi session thật | Đọc Work trước logout 200 → logout 200 → đọc Work/context bằng access cũ 401. Chỉ thu hồi session thử vừa tạo, không logout-all tài khoản. |
| Gateway nội bộ | Ba path authorize/context nội bộ đều bị 404 qua public prefix `/api/work/...`. Không mở route nội bộ ra ngoài. |
| AI từ chối truy cập | Sau pull AI, outsider nhận 403 `TARGET_ACCESS_DENIED`, session thu hồi nhận 401 `AUTHENTICATION_REQUIRED` qua API AI thật. |
| Read-only | Hash và version Project/Task/Sprint qua HTTP trước/sau các yêu cầu AI không đổi. Không apply proposal. |
| Trạng thái cuối | **20/20 runtime container healthy**, AI đã về `staging`, `MOCK_TEST=false`, service key bật. Bản `.env` server tạm khớp byte-for-byte `.env.staging` của repo sau cấu hình. Health không thay thế kết quả nghiệp vụ. |

Các quan sát HTTP không phải số pytest. Không chạy lại toàn bộ suite Work trong
lượt runtime này. Test JWT/session AI mới từ dev đã chạy và đạt; các số suite
Work trước đó nằm trong [kế hoạch](ai-context-implementation-plan.md).

## Kết quả API → queue/worker → LLM thật

Các ca dưới đây dùng endpoint LLM HTTP hiện có, model cấu hình
`gemini-3.8-flash-high`, chỉ đổi môi trường AI tạm thời như đã nêu. Không đổi
budget hoặc model, không fake output. Tên model là cấu hình gửi đi; chưa kiểm
độc lập mapping model phía nhà cung cấp.

| Ca | POST | Trạng thái cuối | Thời gian quan sát từ client |
| --- | --- | --- | --- |
| Backlog Project | 202 | failed — `WORKFLOW_TIMEOUT` | 31,72 giây |
| Phân rã Task | 202 | **succeeded**, 3 subtask; context `task/project` available | 25,55 giây |
| Risk Project | 202 | failed — `WORKFLOW_TIMEOUT` | 31,66 giây |
| Risk Sprint | 202 | failed — `WORKFLOW_TIMEOUT` | 30,69 giây |

Thời gian client gồm POST và polling; không phải phép đo chính xác deadline
nội bộ. Replay giữ cùng request ID: ca thành công trả 200, ca thất bại trả
504 với ID của request cũ, không sinh job mới.

Log metadata worker đã ghi nhận 10 lượt fetch Work, status available/partial,
không error; thời gian riêng các lượt fetch khoảng **66–117 ms**. Ca thất bại
không có context metadata trên response cuối không có nghĩa Work chưa được
gọi: đối chiếu theo request ID trong log worker. Đây là timeout ở budget toàn
workflow AI; chưa phân tích đủ để kết luận nguyên nhân hiệu năng bên trong
model/provider. Không tăng timeout hoặc giảm kiểm quyền để làm báo cáo đạt.

## Hai blocker đã xác minh

1. **JWT trên image AI cũ:** AI dùng `PyJWKClient` không nhận JWKS không có `kid`
   do Identity hiện công bố; token đó vẫn được Work xác thực. Sau pull dev,
   [JwtAuthenticator](../../apps/ai-service/src/infrastructure/security.py#L13)
   chọn một RSA key phù hợp, kiểm JWT và hỏi session-status; đã kiểm lại với
   Identity thật. Không dùng public key tạm hoặc bỏ xác thực.
2. **Endpoint HTTP dưới môi trường staging:**
   [build_litellm_model](../../apps/ai-service/src/infrastructure/providers.py#L28)
   từ chối HTTP ở staging/production, trả `AI_LLM_API_BASE_INVALID` trước khi
   gọi model. Endpoint HTTP thật trả danh mục model 200, nên không gọi đây là
   lỗi mạng hoặc provider Work. Smoke ở development cho phép kiểm đường LLM
   HTTP mà không sửa code; sau khi khôi phục staging, điều kiện chặn này vẫn còn.

## Dữ liệu thử và giới hạn

Dùng các tài khoản/Project thử của stack trước, đăng nhập lại bằng HTTP thật.
Tạo một Task và một Sprint DRAFT mới qua API Work, thêm task vào scope Sprint.
Không chèn hoặc sửa dữ liệu domain bằng SQL. Các target thử được giữ để có thể
poll/replay đối chiếu kết quả; không đụng repository GitHub hoặc dữ liệu người dùng khác.

Chưa kiểm Sprint đóng với service thật, mất membership giữa hai request thật,
race/crash, chất lượng ngữ nghĩa mọi proposal, tải/concurrency hoặc live evaluation
30 ca. Chưa nghiệm thu GitHub trong luồng AI, hosted CI, VPS hay TLS public.
Một ca thành công không chứng minh mọi intent đã ổn định.

Artifact nằm ngoài repo trong thư mục tạm
`utask-work-ai-staging-20261022-4ztvni3y`: deploy exit/digest, provider HTTP,
adapter HTTP, session revoke, kết quả bốn request, metadata context và trạng
thái container. File private credential/raw logs không phải artifact chia sẻ;
báo cáo này chỉ dùng metadata đã lọc, không chứa JWT/key/password.
