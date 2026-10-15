# Phạm vi và quyền truy cập Integration Service

**Trạng thái: Thiết kế mục tiêu, rà soát ngày 15/10/2026.** Đây là chính sách
đề xuất cho bộ [API](api.md) và [sơ đồ](../diagram/integration-service/README.md).
Server Integration chưa triển khai; các quy tắc có bằng chứng phía Work/Identity
được ghi riêng ở cuối tài liệu. Không coi ma trận này là quyền đã được enforce.

## 1. Phạm vi nghiệp vụ

Integration là đầu mối duy nhất gọi GitHub API, phục vụ **thu thập và xác minh
dữ liệu**, gồm GitHub App installation, quyền repository, metadata,
commit/branch/issue/PR, webhook, đồng bộ, OAuth proof và phát sự kiện.

| Integration sở hữu | Service khác sở hữu |
| --- | --- |
| Trạng thái installation, phạm vi GitHub App, dữ liệu GitHub chuẩn hóa | Identity: tài khoản UTask, phiên và liên kết danh tính OAuth |
| Kết nối kỹ thuật project–repository, generation và kết quả xác minh | Work: Project/ProjectMember, quyết định chọn repository, TaskGitHubLink, xác nhận liên kết và tiến độ |
| Delivery webhook, job đồng bộ, outbox và credential kỹ thuật cần thiết | Classroom: nhóm/lớp và phạm vi giảng viên; Work xác minh qua API Classroom |
| Dữ kiện hoạt động nguồn để Work/AI dùng | AI: phân tích/đề xuất; Notification: thông báo cho người nhận |

`ProjectConnection` là trạng thái kỹ thuật Integration thực hiện **theo lệnh
đã được Work cho phép**, không phải quyền quản trị Project. Việc nhận diện
mã task trong branch/commit/PR chỉ tạo dữ kiện/ứng viên; Work kiểm tra và xác
nhận liên kết. Không tạo TaskGitHubLink thứ hai trong Integration.

Phạm vi hiện tại không gồm tạo/sửa issue, PR, comment hoặc push code lên
GitHub; không tự đổi trạng thái Task khi PR merge; không tính điểm, quyết định
đóng góp học tập hoặc chỉ số tiến độ; không quản lý user, vai trò, lớp/nhóm.
Issue là dữ liệu thu thập mục tiêu; xác minh link Issue với Work cần mở rộng
adapter trước, hiện adapter chỉ hỗ trợ branch/commit/PR.

## 2. Ba lớp kiểm tra độc lập

1. **Danh tính caller:** JWT của người dùng, credential riêng của service hoặc
   chữ ký webhook. Mạng backend/gateway không thay xác thực ứng dụng.
2. **Quyền UTask:** Work quyết định action trên đúng Project/Task của user;
   Identity quyết định danh tính và phiên. Role khai báo trong body/JWT chưa
   xác minh, service key và projection cũ không tự cấp quyền tài nguyên.
3. **Quyền GitHub:** installation đang hoạt động, App được cấp repository và
   permission cần thiết. Khi user chọn/liệt kê repository, phải chứng minh
   quyền của chính GitHub user đã liên kết, không dùng quyền App toàn cục.

Với thao tác chọn repository, cả ba lớp phải đạt. Khi đọc context của project
đã kết nối, áp dụng quyền chia sẻ project do Work cho phép và phạm vi GitHub App
hiện hành; không bắt mỗi sinh viên/giảng viên phải tự cài App. Chỉ chia sẻ
metadata/hoạt động được duyệt, không suy từ quyền đọc project thành quyền đọc
source code, secret, token hoặc mọi repository trong installation.

OAuth proof chỉ chứng minh danh tính; không chứng minh quyền quản trị GitHub.
Installation token đại diện App, không đại diện user. GitHub phân biệt quyền
của hai loại token; xem [quyền GitHub App](https://docs.github.com/en/enterprise-cloud%40latest/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).

Nếu không xác minh được quyền, từ chối thao tác cần quyền đó. Không chuyển
sang quyền App toàn cục hoặc coi dữ liệu thiếu thành quyền cho phép.

## 3. Người dùng và quyền nghiệp vụ

**Thiết kế mục tiêu bám theo guard Work hiện có.** Các action project đều
đi qua Work; browser chỉ trực tiếp gọi API cài App và lựa chọn dữ liệu GitHub
được phép xem. Quyền GitHub vẫn được kiểm tra ở Integration.

| Hành động | Điều kiện UTask | Điều kiện bổ sung và nơi quyết định |
| --- | --- | --- |
| Bắt đầu/callback cài App trong luồng Project | Leader ACTIVE của Project có thể ghi, do Work xác nhận | GitHub tự kiểm quyền cài App; callback kiểm state/phiên và installation, chỉ ghi nhận installation, chưa kết nối Project |
| Liệt kê installation/repository để chọn | Leader ACTIVE trong luồng cấu hình Project được Work cho phép | Lọc theo GitHub user đã được Identity xác minh và quyền GitHub hiện hành; không liệt kê tất cả installation của App |
| Chọn/đổi/ngắt repository của Project | Chỉ leader ACTIVE, Project không archived/deleted | Browser gọi Work; Work kiểm quyền trước/sau thao tác; Integration chỉ nhận Work command, kiểm generation và GitHub access. Ngắt kết nối vẫn cho phép khi App đã bị thu hồi quyền |
| Xem metadata kết nối và link Task đã lưu | User có quyền đọc project/task theo Work | Member ACTIVE hoặc giảng viên đúng phạm vi đã được Work xác minh; không mở quyền liệt kê repo private ngoài Project |
| Thêm/xác nhận/gỡ link Task | Member ACTIVE của Project, Task/Project còn có thể ghi | Guard Work hiện không bắt buộc là assignee; giảng viên chỉ có quyền xem không được mutation. Integration chỉ xác minh reference |
| Khai báo GitHub username | Member ACTIVE khai báo cho chính mình qua Work | Không tự đổi `is_github_verified`; thay danh tính đã xác minh phải theo OAuth |
| Nhắc thành viên xác minh GitHub | Leader ACTIVE qua Work | Chỉ phát yêu cầu nhắc; không được liên kết tài khoản hoặc xác minh thay thành viên |
| Liên kết/gỡ OAuth GitHub | User thao tác tài khoản của mình qua Identity | Integration chỉ xử lý yêu cầu exchange do Identity gửi, không nhận code từ browser trên internal API |
| Đồng bộ thủ công | Leader ACTIVE yêu cầu qua Work | Giới hạn tần suất, đúng repo/generation; browser không trực tiếp tạo job nội bộ |
| Đọc GitHub context phục vụ AI | User được Work cho phép đọc dữ liệu Project cho use case AI | AI gọi read-only theo user/target; không được chọn installation, đổi kết nối hay giao job sync |

Vai trò `SYSTEM_ADMIN`, `TEACHER` hoặc GitHub organization owner không tự bỏ
qua điều kiện Project. Không thêm quyền đọc mọi repository/private data cho
admin UTask. Quyền vận hành hạ tầng tách khỏi quyền nghiệp vụ; trường hợp
truy cập đặc biệt cần chính sách riêng và audit trước khi mở.

## 4. Allowlist service và tác nhân kỹ thuật

Các quyền dưới đây là quyền **tối đa theo nhóm API**, không phải một service
key dùng chung có thể gọi toàn bộ Integration.

| Caller | Được gọi/được làm | Không được cấp mặc định |
| --- | --- | --- |
| Identity | `oauth/github/exchange` cho operation/user đã kiểm tra | Liệt kê repository, đổi kết nối, đọc context Project, tạo job sync |
| Work | Chọn/đọc/ngắt connection, verify reference, yêu cầu sync cho Project có quyền | Exchange OAuth thay Identity; truy cập mọi repo của App; tự đặt kết quả GitHub đã xác minh |
| AI | Đọc `github-activity` đã lọc theo Project và user | Command, sync, OAuth exchange, installation/repository enumeration, token GitHub |
| Notification | Nhận event Kafka theo subscription và schema đã chốt | REST đọc toàn bộ GitHub, đọc token hoặc nguồn code |
| GitHub webhook | Gửi delivery đúng App và chữ ký; cập nhật facts/quyền theo loại event | Tạo quyền user, xác nhận Task link hoặc sửa Task trực tiếp |
| Worker/dispatcher/publisher Integration | Đồng bộ hoặc phát outbox trong phạm vi job, repo/generation và credential kỹ thuật | Giả danh user, mở endpoint admin công khai, truy cập database service khác |
| Caller khác/browser vào internal API | Không cho phép | Không dùng JWT hợp lệ của user để thay service credential |

Work/AI gửi cả danh tính service và ngữ cảnh actor được kiểm chứng. Integration
hỏi Work qua REST về **action + target**, không chỉ hỏi user có tồn tại.
Tên action, URL kiểm quyền và cách chuyển actor chưa có contract Integration;
trước khi có, các endpoint phụ thuộc phải đóng. Khi Integration hỏi Work để
xác minh, Work xử lý bằng quyền nội bộ của mình, không gọi vòng lại Integration.

Job hệ thống theo lịch/webhook dùng danh tính worker và phạm vi installation
đã được cho phép, không phụ thuộc JWT user còn sống hay lấy JWT cũ để giả danh.
Job nhận từ user chỉ được tạo sau kiểm quyền lúc tiếp nhận; khi chạy kiểm lại
connection generation, quyền App và chính sách hủy/thu hồi. Kết quả job luôn
được kiểm quyền lại khi đọc; job ID không phải credential.

## 5. Quyền GitHub và dữ liệu tối thiểu

**Đề xuất permission đọc cho giai đoạn thu thập**, cần đối chiếu từng GitHub
endpoint/event được triển khai trước đăng ký App:

| Nhóm GitHub | Quyền đề xuất | Phạm vi sử dụng |
| --- | --- | --- |
| Metadata | Read | Repository, owner, default branch và phạm vi truy cập |
| Contents | Read | Commit/branch cần thiết; không mặc định lấy toàn bộ nội dung file/diff |
| Pull requests | Read | Metadata/trạng thái PR |
| Issues | Read | Metadata/trạng thái issue khi bật chức năng thu thập |
| Administration, Actions, Workflows, Members, quyền ghi | Không yêu cầu mặc định | Chỉ thêm khi có use case và review permission riêng |

Giới hạn token theo repository/permission cần dùng; ưu tiên webhook và
đồng bộ có giới hạn thay vì quét toàn bộ tài khoản. Đây là lựa chọn UTask theo
[nguyên tắc quyền tối thiểu của GitHub](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app),
không khẳng định App thực tế đã có cấu hình này.

Cần có credential ủy quyền theo user hoặc cơ chế GitHub tương đương để chứng
minh tập installation/repository user được truy cập. Mapping `github_user_id`
và proof Identity hiện có không đủ thay thế bước này. Chưa có cơ chế/token
lifecycle đã chốt thì không mở API liệt kê hoặc chọn repo bằng App token toàn cục.

Integration chỉ đọc/ghi DB của mình. Secret/token ở cơ chế lưu bí mật có bảo
vệ và vòng đời rõ ràng, không nằm trong response, Kafka, log, context AI hoặc
ERD nghiệp vụ. Consumer nhận metadata tối thiểu theo hợp đồng; không gửi raw
webhook mặc định. Kafka ACL/topic và retention cần chốt trước vận hành.

## 6. Thu hồi quyền và ranh giới mạng

- Gỡ/suspend App hoặc bỏ repo khỏi installation: ngừng đọc GitHub và cấp dữ
  liệu mới trong phạm vi bị thu hồi, vô hiệu job liên quan, phát facts cho Work
  cập nhật projection; không tự cấp lại quyền qua dữ liệu cũ.
- User rời Project hoặc giảng viên hết phạm vi: Work từ chối đọc/ghi tiếp theo;
  dữ liệu cache, cursor, job hoặc event cũ không cấp quyền trở lại.
- Gỡ OAuth: Identity là nguồn đúng về mapping; không tự gỡ installation dùng
  chung của nhóm. Đóng quyền liệt kê/thao tác GitHub theo danh tính cũ;
  chính sách chia sẻ installation đã được thiết lập cần được xác minh riêng.
- Public allowlist chỉ gồm luồng cài App, danh sách có kiểm quyền, đọc job
  theo scope và webhook. Internal path và route con phải bị chặn tại gateway;
  health endpoint không trả secret hoặc chi tiết GitHub private.
- Hiện Nginx chưa chặn riêng internal Integration; PostgreSQL dùng credential
  chung là khoảng trống hạ tầng, không phải quyền mục tiêu được chấp thuận.

Dữ liệu lịch sử sau thu hồi quyền cần retention và chính sách đọc riêng;
trong khi chưa chốt, không phục vụ qua API nguồn/context Integration cho scope
đã thu hồi. Work xử lý dữ liệu nghiệp vụ đã lưu theo chính sách của Work.

## 7. Bằng chứng hiện trạng và phần còn thiếu

**Một phần — phía gọi đã có source và test; chưa có server Integration:**

- Work [`require_leader`](../../apps/work-service/apps/projects/permissions.py)
  yêu cầu member ACTIVE/LEADER và project ghi được;
  [repository service](../../apps/work-service/apps/integrations/services/repositories.py)
  kiểm lại quyền/generation sau lời gọi adapter.
  Route ngắt kết nối riêng phía Work chưa có; quyền ngắt kết nối trong ma
  trận trên là thiết kế mục tiêu, chưa phải chức năng người dùng đang chạy.
- Work [link guard](../../apps/work-service/apps/integrations/services/links.py)
  yêu cầu thành viên ACTIVE và task/project ghi được;
  [scope đọc](../../apps/work-service/apps/projects/queries/projects.py) nhận
  member ACTIVE hoặc teacher scope do Classroom xác minh, không lấy role từ JWT.
- Work [account service](../../apps/work-service/apps/integrations/services/accounts.py)
  tách khai báo username, dữ kiện xác minh và yêu cầu nhắc xác minh.
- Identity [mapping API](../../apps/identity-service/accounts/views/internal.py)
  chỉ cho caller `integration` đọc mapping GitHub; [test allowlist](../../apps/identity-service/tests/test_api_completion.py)
  kiểm caller khác bị từ chối. API không cấp GitHub access token.
- Identity [OAuth proof client](../../apps/identity-service/authentication/adapters/github_identity_proof.py)
  gọi exchange bằng key riêng. API kiểm tra session hiện allowlist
  `work`, `classroom`, `ai` theo [Identity docs](../identity-service/README.md);
  chưa được giả định Integration gọi được API này. Cách Integration xác minh
  JWT/phiên và nguồn quyền Work cần chốt trước mở public API.

Cần chốt tiếp: contract kiểm quyền action/target và chuyển actor; credential
GitHub theo user và consent; permission App theo endpoint/event; chính sách
thu hồi/lịch sử; timeout và cache quyền; ACL Kafka và secret lifecycle. Mọi
ngoại lệ trong các mục này vẫn là **Chưa triển khai**, không suy từ ma trận
quyền thành hành vi đang chạy.

## 8. Ca kiểm thử quyền bắt buộc khi triển khai

- Leader ACTIVE được chọn repo có quyền; member, outsider, leader đã rời hoặc
  Project đã khóa bị từ chối. Quyền/generation đổi trong lúc gọi GitHub phải
  được kiểm lại trước áp dụng kết quả ở Work.
- Cài App thành công không tạo ProjectConnection. Callback sai state/phiên,
  replay hoặc mất quyền Work bị từ chối; installation ID đoán được không cấp quyền.
- User A không nhìn thấy repo private của user B chỉ vì cùng GitHub App;
  thiếu credential user hoặc quyền GitHub đã thu hồi không được dùng App token
  toàn cục để tiếp tục liệt kê/chọn repo.
- AI đọc đúng Project được cấp quyền; caller AI không gọi được exchange,
  repository-selection, danh sách installation hoặc tạo job. Key Identity,
  Work và AI không thay thế nhau.
- User đọc được metadata Project không nhận token/source code hoặc repo khác;
  member đã rời/teacher hết scope không đọc được context, job hoặc cursor cũ.
- Webhook đúng chữ ký cập nhật facts nhưng không xác nhận Task link; webhook
  sai chữ ký không thay dữ liệu. Job đúng danh tính worker vẫn bỏ kết quả khi
  generation/App access bị thu hồi.
- Ngắt kết nối qua Work vẫn thực hiện được khi App đã bị gỡ; không tự gỡ App
  dùng chung hoặc làm ảnh hưởng kết nối Project khác.

Các ca này là yêu cầu kiểm thử server/adapter trong tương lai; đợt rà soát
tài liệu chỉ kiểm tra nhất quán, link, JSON mẫu và render sơ đồ, không xác nhận
permission runtime Integration.
