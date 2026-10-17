# UTask — Work Service: sơ đồ tuần tự

**Phiên bản:** 7.0 — rà soát theo source Plane và thiết kế gọn ngày 08/10/2026.
**Trạng thái: Thiết kế mục tiêu**, chưa có Work runtime để nghiệm thu.

Nguồn chuẩn: [system](../../system/README.md), [Work API](../../architecture/Work_Service_API_Specification.md), [PRD](../../architecture/UTask%20-%20Phân%20tích%20thiết%20kế%20yêu%20cầu.md), [ERD 20 bảng](erd.md), [BFD](bfd.md), [Use Case](usecase.md).

## 1. Quy ước đọc và kiểm chuẩn

- Mỗi sơ đồ là `sequenceDiagram`: actor, lifeline, message, response, nhánh alt/else hoặc opt và thứ tự xử lý. Flowchart không được gắn nhãn Sequence.
- Request người dùng luôn qua API: kiểm JWT/session-status và resource scope trước command. Các bước auth chung được ghi trong message/ghi chú; không giả định gateway đã cấp quyền. Permission hiện hành còn được kiểm trong transaction.
- REST/LLM/storage validation ngoài transaction; protocol khóa Project → State/Sprint/Task theo ID áp dụng mọi Work writer. Nhánh lỗi sau BEGIN phải ROLLBACK và không đi tiếp đường ghi thành công.
- Receipt request và event dedup là hạ tầng trong thiết kế mục tiêu; attachment dùng một Attachment PENDING/CONFIRMED/EXPIRED. Project.current_task_sequence là counter, Activity chung có đúng một subject FK, CommentMention là quan hệ M:N.
- DB chỉ lưu Outbox; process publisher mới phát Kafka và nhận ACK. `-)` biểu diễn message bất đồng bộ, `-->>` biểu diễn response. Publisher/consumer chạy độc lập, có thể xử lý trước hoặc sau HTTP response sau DB commit; diagram chỉ minh họa một lịch thực thi. Event tự đến độc lập với request; không dùng Kafka để hỏi-đáp đồng bộ.
- Các diagram rút gọn body/query và response envelope; API là nguồn whitelist/route/schema chi tiết. Mã Task hiển thị không thay UUID path. Có lỗi DB thì toàn transaction rollback; không gọi test/render thành bằng chứng runtime đã chạy.
- Với mọi command có receipt: kiểm quyền hiện hành trước đọc kết quả; key/item đã có nhưng hash khác thì conflict và rollback. Chỉ command mới kiểm expected_version rồi ghi; replay đã commit không chạy lại mutation hoặc kiểm điều kiện chuyển trạng thái của lần đầu.

## 2. Danh mục luồng

| Số | Luồng | Trọng tâm đã kiểm |
| --- | --- | --- |
| 1 | Tạo Task backlog | Leader, FK/assignment validation, Project counter, atomic audit/outbox/receipt |
| 2 | Transition/reorder | Assignee/Leader, version, completion/reopen, rank và rollback |
| 3 | Block/unblock | Lý do, membership, terminal policy, không đổi workflow |
| 4 | Close Sprint/rollover | Snapshot facts trước di chuyển, membership history, publisher tách DB |
| 5 | Dependency | Sequence thật, permission trước normalize, project graph lock và cycle rollback |
| 6 | AI backlog | User gọi nhóm AI, Work human apply/provenance/receipt |
| 7 | AI subtask/context Work | Context Kafka job bất đồng bộ, Work apply đúng Task được giao |
| 8 | GitHub activity/confirm | Integration DB/outbox, consumer dedup, pending candidate và user confirm |
| 9 | Teacher feedback | Classroom scope ngoài TX, mention diff/audit, Notification sau event |
| 10 | Project setup | Group Leader, snapshot membership, default states, counter và uniqueness |
| 11 | Chọn repository | Integration source authority, operation replay, projection lag/reconcile |
| 12 | Attachment | Một hàng từ presign tới confirm/download, owner/key/expiry và retry |

### 2.1. Sequence 1 — Tạo Task backlog

Tham khảo validation → save → response của Plane; Work bổ sung Leader-only, Project counter và audit/outbox/receipt chung transaction. Tạo subtask/AI apply có policy riêng ở 7/6.

```mermaid
sequenceDiagram
    autonumber
    actor L as Leader
    participant A as Work API
    participant S as Task command
    participant D as Work DB
    L->>A: POST /projects/{project_id}/tasks/ + Idempotency-Key
    A->>A: JWT, session-status, scope và serializer
    alt Auth hoặc dữ liệu đầu vào không hợp lệ
        A-->>L: 401/403/404/400, không mutation
    else Request hợp lệ
        A->>S: Actor và dữ liệu hợp lệ
        S->>D: BEGIN, project barrier, claim receipt
        alt Receipt đã hoàn tất, body hash trùng sau current quyền
            S->>D: COMMIT giao dịch không đổi dữ liệu
            S-->>A: Response receipt sau kiểm quyền hiện hành
            A-->>L: Replay kết quả
        else Request mới
            S->>D: Kiểm lại Leader, project write và State/Epic/Label/assignee cùng scope ACTIVE
            alt Scope hoặc quyền đã đổi
                S->>D: ROLLBACK
                S-->>A: Lỗi domain
                A-->>L: 403/404/422 envelope
            else Domain hợp lệ
                S->>D: UPDATE Project.current_task_sequence + 1 RETURNING
                S->>D: Task, Assignment, Label, Activity, Outbox, Receipt
                S->>D: COMMIT
                S-->>A: Task chính thức
                A-->>L: 201 envelope
            end
        end
    end
```

### 2.2. Sequence 2 — Transition và reorder Kanban

Plane đồng bộ completed_at khi state đổi; UTask phân biệt vào COMPLETED, chuyển giữa các cột COMPLETED và reopen. Neighbor ID/rank/revision là policy UTask, không coi paginator offset Plane là cursor board này.

```mermaid
sequenceDiagram
    autonumber
    actor U as Assignee ACTIVE hoặc Leader
    participant A as Work API
    participant W as Workflow command
    participant D as Work DB
    U->>A: PATCH /tasks/{task_id}/transition/ với expected_version và neighbor IDs
    A->>A: JWT/session, scope, whitelist input
    A->>W: Lệnh chuyển state hoặc vị trí
    W->>D: BEGIN, Project rồi State/Sprint/Task theo protocol
    W->>D: Kiểm quyền hiện hành, version, target và neighbor cùng scope
    alt Không có quyền hoặc vị trí/version không còn hợp lệ
        W->>D: ROLLBACK
        W-->>A: Permission hoặc VERSION_CONFLICT
        A-->>U: 403/404/409, yêu cầu tải lại
    else Hợp lệ
        opt Khoảng rank không đủ
            W->>D: Rebalance cột dưới cùng lock
        end
        W->>W: Tính rank và completion theo state group trước/sau
        W->>D: Task version, board_revision, Activity và Outbox
        W->>D: COMMIT
        W-->>A: State/rank/version chính thức
        A-->>U: 200 envelope
    end
```

### 2.3. Sequence 3 — Block hoặc unblock

Blocked là cờ do người dùng ghi, không tự đổi state; tín hiệu dependency/overdue do Work rules tính riêng. Bật blocked trên terminal Task bị từ chối; unblock không sửa state.

```mermaid
sequenceDiagram
    autonumber
    actor U as Assignee ACTIVE hoặc Leader
    participant A as Work API
    participant D as Work DB
    U->>A: PATCH /tasks/{task_id}/block/ hoặc unblock/
    A->>A: JWT/session, scope, input và reason khi block
    A->>D: BEGIN, Project barrier và Task lock
    A->>D: Kiểm membership/quyền và state hiện hành
    alt Không có quyền, thiếu reason hoặc block terminal Task
        A->>D: ROLLBACK
        A-->>U: 403/404/400 envelope
    else Hợp lệ
        A->>D: Manual blocked/reason, version, board_revision, Activity, Outbox
        A->>D: COMMIT
        A-->>U: 200 envelope, workflow giữ nguyên
    end
```

### 2.4. Sequence 4 — Close Sprint và rollover (P1)

Học thứ tự snapshot-before-transfer của Plane. UTask giữ hàng membership lịch sử thay vì đổi cycle_id trên hàng cũ. Source phải ACTIVE; với một ACTIVE/project, target kế tiếp hợp lệ trong MVP là DRAFT hoặc backlog, không một ACTIVE thứ hai.

```mermaid
sequenceDiagram
    autonumber
    actor L as Leader
    participant A as Work Sprint API
    participant D as Work DB
    participant Pub as Work Outbox publisher
    participant K as Kafka
    L->>A: POST /sprints/{sprint_id}/close/ + key, target hoặc null
    A->>A: JWT/session, scope và input
    A->>D: BEGIN, Project và State/Sprint/Task theo protocol
    A->>D: Quyền hiện hành, lookup receipt và so semantic hash
    alt Receipt đã commit, payload trùng
        A->>D: COMMIT không đổi dữ liệu
        A-->>L: Replay kết quả, không close hoặc rollover lại
    else Key đã dùng với payload khác
        A->>D: ROLLBACK
        A-->>L: 422 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD
    else Command mới
        A->>D: Kiểm ACTIVE source, DRAFT target cùng project và version
        alt Quyền/version/target sai
            A->>D: ROLLBACK
            A-->>L: 403/404/409/400 envelope
        else Hợp lệ
        A->>D: Chốt một closure_snapshot facts và metric/formula_version trước thay membership
        A->>D: Kết thúc membership nguồn, facts cuối kỳ chỉ ở snapshot
        alt Target Sprint DRAFT
            A->>D: Tạo membership đích chỉ cho Task chưa COMPLETED/CANCELLED
        else Backlog
            Note over A,D: Không tạo membership mới, không đổi state Task
        end
        A->>D: Sprint COMPLETED, Activity, closure Outbox và Receipt
        A->>D: COMMIT
        A-->>L: 200, Sprint đã đóng
        Pub->>D: Đọc Outbox đã commit theo project sequence
        Pub-)K: Publish closure facts
        K-->>Pub: Delivery ACK
        Pub->>D: Mark published sau ACK
        Note over A,D: Snapshot facts/metric đã chốt trong Work, dashboard không chờ AI
        end
    end
```

Receipt replay dùng protocol chung mục 1.5 của Work API, không close lại hoặc tạo membership lần hai. Lỗi publisher chỉ để Outbox pending/retry, không rollback Sprint đã commit; dashboard phân biệt báo cáo chưa cập nhật.

### 2.5. Sequence 5 — Dependency canonical và kiểm cycle

Plane đảo chiều relation khi nhận tên nghịch đảo, nhưng cho relation xuyên project trong workspace ở đường đã đọc. UTask giữ same-project/DAG. Permission kiểm trên Task trong URL trước khi chuẩn hóa BLOCKED_BY, không vô tình buộc Member phải được giao cả task target.

```mermaid
sequenceDiagram
    autonumber
    actor U as Assignee Task trong URL hoặc Leader
    participant A as Work Relation API
    participant D as Work DB
    U->>A: POST /tasks/{task_id}/relations/ với type và related_task_id
    A->>A: Auth/scope, input type và quyền Task trong URL
    A->>D: BEGIN, Project graph barrier và Task theo ID
    A->>D: Kiểm hai task cùng project, không deleted, quyền hiện hành
    A->>A: BLOCKED_BY đổi chiều, DUPLICATE/RELATES_TO sắp cặp UUID
    opt Relation canonical là BLOCKS
        A->>D: Reachability target tới source trên active edges, loại cạnh cũ khi update
    end
    alt Sai scope, self-relation hoặc tạo cycle
        A->>D: ROLLBACK
        A-->>U: 404/400 hoặc 409 DAG_CYCLE_DETECTED
    else Hợp lệ
        A->>D: Relation canonical không copied project, Activity subject Task URL, Outbox
        A->>D: COMMIT
        A-->>U: 201 envelope
    end
```

RELATES_TO/DUPLICATE kiểm scope nhưng không đi vào DAG. Delete/update/restore/AI batch cùng barrier; relation lookup chấp nhận Task URL là một trong hai đầu cạnh, không bỏ sót BLOCKED_BY vì lưu chiều canonical.

### 2.6. Sequence 6 — User gọi nhóm AI, Work áp dụng backlog đã duyệt

AI Service/AIDB do nhóm khác phụ trách, được vẽ như một hệ thống ngoài ranh giới Work. Không áp đặt schema AI, job nội bộ hoặc quyền truy cập từ một sơ đồ Work. Work chỉ chịu context export và mutation đã được user duyệt. API AI là hợp đồng cần nhóm AI cung cấp, chưa có source trong repo.

```mermaid
sequenceDiagram
    autonumber
    actor L as Leader
    participant AI as Nhóm AI - API và nơi lưu kết quả
    participant W as Work apply API
    participant D as Work DB
    participant Pub as Work publisher
    participant K as Kafka
    L->>AI: Yêu cầu đề xuất backlog, nhận reference theo contract AI
    Note over AI,K: Context nhận qua Kafka, job nội bộ và lưu do nhóm AI làm
    AI-->>L: Trạng thái/kết quả proposal theo contract, không tạo Task Work
    L->>AI: Xem, sửa và chọn item đề xuất
    AI-->>L: Proposal/item reference và revision đã duyệt
    opt User bấm áp dụng
        L->>W: POST /projects/{project_id}/tasks/bulk-apply-ai/ + key
        W->>W: JWT/session, scope, whitelist input
        opt Contract chọn kiểm provenance bằng backend read-only
            W->>AI: Kiểm binding project, proposal/item/revision ngoài transaction
            AI-->>W: Proof hoặc denied/unavailable
        end
        alt Không xác minh được provenance/quyền
            W-->>L: 403/404/503, không mutation
        else Source binding hợp lệ
            W->>D: BEGIN, Project barrier, current quyền rồi receipt lookup
            W->>D: So hash bất biến từng item cũ, chỉ item mới kiểm version/local refs/DAG
            alt Batch sai, stale hoặc vượt quyền
                W->>D: ROLLBACK
                W-->>L: 400/403/409, không tạo một phần
            else Batch hợp lệ hoặc replay
                W->>D: Counter/Task/hash/audit/outbox cho item mới, receipt hoặc replay no-op
                W->>D: COMMIT
                W-->>L: Kết quả đã commit với affected IDs/proposal refs
                Pub->>D: Đọc event apply đã commit
                Pub-)K: work.ai_proposal.applied - contract mục tiêu
                K-->>Pub: ACK
                Pub->>D: Mark published
                K-)AI: Bằng chứng Work commit, nhóm AI cập nhật hiển thị
            end
        end
    end
```

Mất response/event sau commit: dùng receipt/provenance lookup/replay, không tạo mutation mới. User chỉ xem/sửa draft không làm Work ghi report. AI không tự báo APPLIED vì user bấm nút. Schema proof/event/reconcile phải được hai nhóm thống nhất; sơ đồ không chứng minh AI đã triển khai.

### 2.7. Sequence 7 — Subtask đã duyệt và context Work bất đồng bộ

User gọi AI theo contract nhóm AI. Work nhận request context qua Kafka nếu contract chọn snapshot bổ sung; worker chỉ export dữ liệu Work và không chờ agent chạy LLM. Khi apply, Member chỉ làm trên task cha được giao, không dùng AI để đổi assignee/estimate/deadline hoặc state parent.

```mermaid
sequenceDiagram
    autonumber
    actor U as Assignee Task cha hoặc Leader
    participant AI as Nhóm AI - API và nơi lưu kết quả
    participant K as Kafka
    participant C as Work context consumer
    participant D as Work DB
    participant Pub as Work publisher
    participant W as Work apply API
    U->>AI: Yêu cầu phân rã Task, nhận job reference theo contract
    opt Context Work thiếu, hai nhóm chọn bổ sung snapshot
        AI-)K: Context request có reference, scope proof, deadline
        K-)C: Request cho source Work
        C->>C: Validate producer/schema và quyền được thống nhất
        alt Không được phép hoặc request hết hạn
            C->>D: Transaction lưu rejection Outbox và dedup request
            Pub->>D: Đọc rejection Outbox đã commit
            Pub-)K: Response từ chối có correlation theo contract
            K-->>Pub: ACK
            Pub->>D: Mark published
        else Request hợp lệ
            C->>D: Transaction snapshot nhất quán và dedup/outbox
            D-->>C: Source facts/version đã lưu bền
            Pub->>D: Đọc snapshot response Outbox
            Pub-)K: work.context.available, chunks/complete marker nếu lớn
            K-->>Pub: ACK
            Pub->>D: Mark published
            K-)AI: Context Work có captured_at/source version
        end
    end
    Note over AI,K: Ghép context, timeout, LLM và lưu kết quả thuộc nhóm AI
    AI-->>U: Proposal/items để user xem, sửa và chọn
    U->>W: POST /tasks/{task_id}/subtasks/bulk-apply-ai/ + key
    W->>W: Auth/scope, source binding theo contract và whitelist
    W->>D: BEGIN, Project/Task locks, current quyền rồi receipt lookup
    W->>D: So ai_payload_hash item cũ, kiểm version/whitelist/DAG cho item mới
    alt Mất quyền, source không hợp lệ hoặc batch sai
        W->>D: ROLLBACK
        W-->>U: 403/404/409/400
    else Hợp lệ hoặc replay
        W->>D: Counter, Subtasks, Activity, Outbox, Receipt hoặc no-op
        W->>D: COMMIT
        W-->>U: Kết quả đã commit, parent state giữ nguyên
    end
```

Snapshot export không đọc DB Classroom/Integration. Request event không tự cấp quyền, dedup/offset sau effect commit hoặc response rejection lưu bền/ACK. Context timeout thuộc nhóm AI, không Work HTTP query chờ Kafka. Result apply được trả/phát theo Sequence 6. Agent không gọi Work REST/DB lấy context.


### 2.8. Sequence 8 — GitHub event, candidate và user confirm

Integration là owner provider. Tách Integration DB/publisher, Work consumer và Work API; DB không gửi Kafka, consumer không nhận command người dùng. Cùng event_id/hash dedup, source version/generation bảo vệ stale updates.

```mermaid
sequenceDiagram
    autonumber
    participant G as GitHub
    participant I as Integration API
    participant IDB as Integration DB
    participant IP as Integration publisher
    participant K as Kafka
    participant W as Work consumer
    participant D as Work DB
    actor U as Member hoặc Leader
    participant A as Work API
    G->>I: Webhook delivery
    I->>I: Signature, repo scope, schema
    I->>IDB: Delivery dedup và facts/Outbox trong transaction
    IDB-->>I: COMMIT hoặc delivery đã xử lý
    I-->>G: ACK sau lưu bền
    IP->>IDB: Đọc Outbox pending
    IP-)K: Normalized github event
    K-->>IP: Delivery ACK
    IP->>IDB: Mark published
    K-)W: Event activity
    W->>W: Validate envelope/producer/version
    alt Schema/event không hợp lệ
        W-)K: Publish DLQ với lỗi đã làm sạch
        K-->>W: DLQ ACK
        W->>K: Commit input offset sau ACK
    else Event hợp lệ
        W->>D: BEGIN, Project barrier, claim consumed event
        alt Thiếu prerequisite hoặc cần reconcile source
            W->>D: ROLLBACK
            Note over W,K: Retry/reconcile, không commit input offset
        else Scope và source được quyết định hợp lệ
            alt Duplicate hoặc source version đã cũ
                W->>D: Không apply effect, giữ receipt nhất quán
            else Event mới
                alt Link đã CONFIRMED
                    W->>D: Cập nhật metadata nguồn
                else Task code là gợi ý mới
                    W->>D: Candidate PENDING, không official link
                end
                W->>D: Activity khi có thay đổi và consumed receipt
            end
            W->>D: COMMIT
            W->>K: Commit offset
        end
    end
    U->>A: POST /tasks/{task_id}/github-links/{link_id}/confirm/ + key
    A->>A: Auth/session và project scope
    A->>D: BEGIN, Project/link lock, receipt, kiểm generation/quyền
    alt Repo bị ngắt hoặc không có quyền
        A->>D: ROLLBACK
        A-->>U: 403/404/409
    else Confirm mới hoặc đã confirmed hợp lệ
        A->>D: Confirm cùng link hoặc no-op, Activity/Outbox/Receipt
        A->>D: COMMIT
        A-->>U: 200 envelope
    end
    Note over A,D: PR MERGED không tự đổi Task state
```

Duplicate delivery không tạo Outbox mới ở Integration. Event thiếu prerequisite/project/source snapshot phải retry/reconcile dưới rollback, không coi là nhánh “repo hợp lệ”. DB lỗi không commit offset. Consumer duplicate khác hash hoặc unsupported version không ghi PROCESSED. Hủy/link thủ công vẫn qua Work API theo scope.

### 2.9. Sequence 9 — Teacher feedback và mention

Plane comment: permission → serializer → save → background activity. Work bổ sung Teacher đúng lớp, CommentMention và Activity/Outbox atomic; feedback không đổi kế hoạch Task.

```mermaid
sequenceDiagram
    autonumber
    actor T as Teacher
    participant A as Work Comment API
    participant C as Classroom API
    participant D as Work DB
    participant Pub as Work publisher
    participant K as Kafka
    participant N as Notification
    T->>A: POST /comments/ với đúng một subject project HOẶC task
    A->>A: JWT/session, Task/Project scope và serializer
    A->>C: Kiểm Teacher phụ trách group và recipients cần scope lớp
    C-->>A: Scope proof/version hoặc denied/unavailable
    alt Không đủ quyền hoặc không xác minh được
        A-->>T: 403/404/503, không mở mutation transaction
    else Scope hợp lệ
        A->>D: BEGIN, Project barrier và local scope recheck
        alt Local scope hoặc proof đã đổi/hết hạn
            A->>D: ROLLBACK
            A-->>T: 403/409, không ghi feedback
        else Local scope còn hợp lệ
            A->>D: Comment, CommentMention, Activity subject Comment, Outbox
            A->>D: COMMIT
            A-->>T: 201 envelope
            Pub->>D: Đọc Outbox đã commit
            Pub-)K: teacher.feedback.added với data/recipients
            K-->>Pub: Delivery ACK
            Pub->>D: Mark published
            K-)N: Comment/mention event
            N->>N: Dedup event/recipient, gửi theo kênh
        end
    end
```

Nếu local scope/proof đã đổi hoặc DB constraint fail dưới lock thì rollback, không trả 201. Edit giữ diff người được nhắc và chỉ phát recipients mới; cùng audit history. Scope proof có expiry/version, REST không tạo strong consistency xuyên DB.

### 2.10. Sequence 10 — Tạo project từ group

Plane tạo Project → creator member → default states. UTask khác quyền: Group Leader đã được Classroom xác nhận và kế thừa toàn bộ membership/role nguồn, không tự nâng một Member.

```mermaid
sequenceDiagram
    autonumber
    actor L as Group Leader
    participant A as Work Project API
    participant C as Classroom API
    participant D as Work DB
    L->>A: POST /projects/ + Idempotency-Key
    A->>A: JWT/session và validate đề tài/group
    A->>C: Xác minh group, Group Leader, members/roles và source version
    C-->>A: Snapshot hợp lệ hoặc denied/unavailable
    alt Không xác minh được hoặc không phải Group Leader
        A-->>L: 403/503, không tạo Project
    else Snapshot hợp lệ
        A->>D: BEGIN, claim receipt và uniqueness group/identifier
        alt Replay đã hoàn tất
            A->>D: COMMIT không đổi dữ liệu
            A-->>L: Response đã lưu sau kiểm quyền
        else Khởi tạo mới
            A->>D: Project counter=0, ProjectMember từ snapshot, default State
            A->>D: Activity subject Project, Outbox, Receipt
            A->>D: COMMIT
            A-->>L: 201 envelope
        end
    end
```

Unique conflict/DB lỗi rollback toàn bộ, không có project thiếu State/Member. Group thay đổi sau verify được xử lý bằng source version/reconcile; không có FK hoặc transaction xuyên Classroom DB. Membership consumer cập nhật Work bằng source version dưới Project barrier, cùng activity/outbox/dedup.

### 2.11. Sequence 11 — Chọn repository qua Integration

Luồng GitHub App/OAuth của UTask, không sao chép lời gọi provider trong monolith Plane vào Work. Integration là source connection; operation_id cho retry, expected generation cho concurrent change.

```mermaid
sequenceDiagram
    autonumber
    actor L as Leader
    participant A as Work facade
    participant I as Integration API
    participant G as GitHub
    participant IDB as Integration DB
    participant D as Work DB
    L->>A: POST /projects/{project_id}/github/repository/ với operation_id
    A->>A: JWT/session, Leader và scope/version hiện hành
    A->>I: Command chọn repo, actor proof, expected generation
    I->>I: Kiểm caller/proof, operation replay và source generation
    I->>G: Xác minh quyền/cài đặt qua provider API
    G-->>I: Repo metadata/quyền hoặc lỗi
    alt Không được cấp quyền hoặc provider unavailable
        I-->>A: Denied hoặc unavailable
        A-->>L: 403/503, không tự lưu repo mới
    else Operation được lưu ở source
        I->>IDB: Connection/operation/Outbox trong transaction
        IDB-->>I: COMMIT hoặc replay cùng operation_id
        I-->>A: Source result hoặc PENDING
        A->>D: Transaction cập nhật projection khi version/generation mới
        alt Source/projection chưa hoàn tất
            A-->>L: 202 operation pending, GET để theo dõi
        else Projection đã CONNECTED
            A-->>L: 200 với source metadata/generation
        end
        Note over IDB,D: Source event và reconcile sửa lag/crash, không atomic hai DB
    end
```

Không giữ Work transaction trong lúc gọi Integration/GitHub. Receipt replay có thể trả source result cũ sau kiểm quyền mà không gọi provider; Response/Event cũ không ghi đè source mới; repo cũ/link cũ giữ lịch sử. Work DB lỗi sau Integration commit cần reconcile theo operation_id, không tuyên bố provider connection đã rollback. Group/Leader permission đã mất lúc cập nhật phải xử lý theo source proof và policy ownership, không cấp quyền từ metadata client.

### 2.12. Sequence 12 — Tệp Task/Project: upload, confirm và download

resource_path là `/tasks/{task_id}` hoặc `/projects/{project_id}`; server resolve đúng một subject, không nhận hai owner từ body.

Plane FileAsset được tạo trước presign và cập nhật is_uploaded sau đó; UTask học vòng đời một hàng, nhưng thêm owner/subject/expiry/content validation và CONFIRMED-only scope.

```mermaid
sequenceDiagram
    autonumber
    actor U as Member ACTIVE
    participant A as Work Attachment API
    participant D as Work DB
    participant R as R2 hoặc local storage
    U->>A: POST resource_path/attachments/presigned-url/ cho Task hoặc Project
    A->>A: Auth/scope, MIME/size validation
    A->>D: Transaction tạo Attachment PENDING, một subject Task hoặc Project, owner/key/expiry
    A->>R: Sinh presigned PUT cho key đã cấp
    A-->>U: attachment_id, upload_url, expiry
    U->>R: PUT object
    U->>A: POST resource_path/attachments/ với attachment_id + key
    A->>D: Đọc status/owner/subject và receipt dưới scope hiện hành
    alt CONFIRMED và replay hợp lệ
        A-->>U: Cùng attachment_id sau kiểm quyền, không HEAD lại
    else PENDING thuộc đúng actor và subject
        A->>R: HEAD/content validation với metadata đã cấp
        R-->>A: Object facts hoặc lỗi
        alt Object thiếu hoặc metadata/content sai
            A-->>U: 400 hoặc 503, không CONFIRMED
        else Object hợp lệ
            A->>D: BEGIN, Project/Task/Attachment lock và claim request receipt
            A->>D: Kiểm lại owner/subject/expiry/status/quyền
            alt Expired hoặc scope không còn hợp lệ
                A->>D: ROLLBACK
                A-->>U: 400/403/404
            else PENDING hoặc đã confirm đồng thời hợp lệ
                A->>D: UPDATE cùng hàng CONFIRMED, Activity, Outbox, Receipt hoặc no-op
                A->>D: COMMIT
                A-->>U: 201/200 cùng attachment_id
            end
        end
    else Sai owner/subject hoặc EXPIRED
        A-->>U: 403/404/400, không cấp URL hoặc confirm
    end
    U->>A: GET resource_path/attachments/{attachment_id}/download/
    A->>D: Scope hiện hành và status CONFIRMED chưa deleted
    alt Được phép
        A->>R: Sinh signed download ngắn hạn
        A-->>U: URL có hạn
    else Không được phép hoặc chưa confirmed
        A-->>U: 403/404, không URL
    end
```

`key` trong lệnh confirm là Idempotency-Key header, không là storage_key client chọn. Retry CONFIRMED kiểm quyền/receipt trước khi yêu cầu HEAD lại; không INSERT attachment thứ hai. Presign lỗi để PENDING cleanup, không giả đã upload. Chỉ CONFIRMED được list/count/download; signed PUT có thể còn hạn sau confirm nên storage immutability/checksum/version policy phải được chốt khi tích hợp R2, không coi HEAD metadata là toàn bộ bảo vệ nội dung.

## 3. Đối chiếu mã Plane và giới hạn kế thừa

Source đã đọc: nhánh preview, commit **7466675e471efe1c96b122615f7a0d30c9b2eb05**. Không chạy Plane runtime; đây là bằng chứng source tại một snapshot.

| Luồng | Source Plane | Điều được kế thừa / khác biệt UTask |
| --- | --- | --- |
| Task create | [Issue create](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/app/views/issue/base.py#L405), [serializer validation](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/api/serializers/issue.py#L110) | Permission/validation trước save. Plane cho member tạo; UTask backlog Leader-only. |
| Sequence allocator | [Issue.save](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/db/models/issue.py#L180) | Plane advisory lock + Max ledger; UTask Project counter dưới barrier đã có, không thêm bảng một-hàng/project. |
| Completion/board | [completion hook](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/db/models/issue.py#L240), [grouped offset](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/utils/paginator.py#L195) | Hook xử lý completion/reopen; UTask giữ mốc khi đổi cột cùng COMPLETED và có board revision riêng. |
| Sprint rollover | [transfer snapshot/links](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/utils/cycle_transfer_issues.py#L410) | Snapshot trước transfer. Plane update cycle_id trên link; UTask kết thúc membership cũ/tạo mới, giữ history, Work tính metric nội bộ. |
| Dependency | [relation create](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/app/views/issue/relation.py#L209) | Có chuẩn hóa chiều, workspace scope; UTask same-project/DAG lock, không chứng minh cycle detector UTask từ Plane. |
| Comment/activity | [comment create](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/app/views/issue/comment.py#L64) | Scope/serializer/save trước background task. UTask audit/Outbox cùng mutation TX; không sao chép delay call rồi hứa durability. |
| Project setup | [Project create](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/app/views/project/base.py#L257) | Creator membership/default State; UTask xác minh Classroom Group Leader và kế thừa membership, không Admin creator bất kỳ. |
| Attachment | [FileAsset create/presign](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/app/views/asset/v2.py#L116), [confirm và project access](https://github.com/makeplane/plane/blob/7466675e471efe1c96b122615f7a0d30c9b2eb05/apps/api/plane/app/views/asset/v2.py#L418) | Học vòng đời asset một hàng trước/sau upload; không suy ra Plane có đúng receipt/expiry/content validation của UTask. |
| AI/GitHub integrations | Không có bằng chứng ở các đường source trên cho ownership/context/event như UTask | Tuân theo docs/system và PRD UTask, không gắn nhãn “kế thừa Plane” cho thiết kế chưa được source chứng minh. |

## 4. Kết quả rà soát và điều kiện triển khai

Phạm vi Work: nội bộ AI/AIDB do nhóm khác. Đã sửa ở tầng thiết kế: Sequence 5 flowchart → sequence, nhánh rollback, tách publisher khỏi DB, api/consumer khác lifeline, Project counter/Activity/Attachment mới, COMPLETED/CANCELLED policy, context-not-ready, human apply, source authority và thêm 3 luồng còn thiếu.

[Mermaid Sequence syntax](https://mermaid.js.org/syntax/sequenceDiagram.html) hỗ trợ actor/lifeline, message/response, alt/else, opt và message async được dùng ở đây. Render pass chỉ xác nhận cú pháp; review source/API/ERD mới kiểm ý nghĩa. Không gọi tài liệu đạt 100% nghiệp vụ hoặc xác nhận implementation.

Khi có code: test auth/IDOR, same-project, rollback/crash/replay, closure concurrent writer, graph cycle concurrent, Kafka ACK/DLQ/source versions, attachment Task/Project expiry/overwrite và provider thật. Quyết định Work về bảng/cardinality/quyền/snapshot đã ghi ở API/ERD và audit mục 6; hợp đồng proof/order/reconcile liên nhóm cần phối hợp, còn runtime phải chứng minh thực thi đúng các lựa chọn đó.

## 5. Ranh giới đã thống nhất trong lần sửa này

Không có service tiến độ riêng; Work query/job tính số liệu trên Work DB. User gọi AI API do nhóm AI phụ trách, Work không tạo job/lưu report. Schema/provenance/context-request/result-event cần contract hai nhóm trước implementation. [Work–AI boundary](../../project-service/ai-boundary-contract.md).


## 6. Quy tắc schema được audit trước implementation

- Comment và Attachment ghi đúng một FK subject; project response của Task comment là field suy ra. Activity giữ đúng một subject, nguồn history không bị hard-delete State/Epic/Label.
- Close Sprint chốt facts vào một closure_snapshot, SprintTask chỉ timeline/lý do ADD và REMOVE riêng; không is_scope_creep persisted hay bản snapshot thứ hai trên junction.
- TaskRelation scope suy từ Task, loại vô hướng canonical theo UUID, permission trước normalize. Work provenance scalar, không JSON chứa dữ liệu AI.
- Receipt/replay sau current permission **trước** expected version cho mutation mới; replay đã có không fail vì chính lần apply đầu đã tăng version. AI cùng item/actor/key khác lookup cùng operation, không hai row authoritative.
- AI/Integration/Identity ordered-source contracts chưa có code phải được xác nhận; source event_id hoặc lúc nhận không tự là entity version.

Các nhánh/schema này được đối chiếu tại [ERD audit](../../project-service/erd-audit-20261008.md); render không thay test concurrency.
