# UTask – Work Service Use Case Diagrams & Detailed Specifications
## Hệ thống Sơ đồ Use Case Phân hệ và Đặc tả Kịch bản Nghiệp vụ Chi tiết (Định dạng PlantUML)

**Phiên bản:** 6.0 (Đồng bộ 08/10/2026)  
**Trạng thái:** Thiết kế mục tiêu — chưa xác minh runtime  
**Service:** `apps/work-service`  
**Tài liệu tham chiếu:**
- [BFD Specification](bfd.md) (Sơ đồ Phân rã Chức năng Nghiệp vụ)
- [docs/architecture/UTask - Phân tích thiết kế yêu cầu.md](../../architecture/UTask%20-%20Phân%20tích%20thiết%20kế%20yêu%20cầu.md) (Source of Truth nghiệp vụ)
- [erd.md](erd.md) (20 bảng mục tiêu, từ điển cột và constraint minh họa)  
**Repository tham khảo thực tế:** [Plane](https://github.com/makeplane/plane) (`apps/api/plane/`)

---

## 1. Danh sách Tác nhân (Actors) & Quyền hạn Hệ thống

Hệ thống `work-service` tương tác trực tiếp với 5 tác nhân chính:

1. **Sinh viên / Thành viên nhóm (Student Member):**
   - Thực thi các công việc được phân công (`task.assignments.contains(user)`).
   - Được phép chuyển đổi trạng thái trên Kanban đối với **task của mình** (US-3.3).
   - Đánh dấu task bị **Blocked** và nhập lý do (US-3.3).
   - Yêu cầu AI phân rã sub-task cho công việc mình phụ trách (US-5.5).
   - Liên kết hoạt động GitHub với task (US-5.2) và tham gia thảo luận comment (US-4.1).
   - *Không có quyền:* Không tạo task trong backlog, không đổi assignee/deadline/trạng thái task của người khác.

2. **Trưởng nhóm sinh viên (Team Leader / Project Owner):**
   - Có toàn bộ quyền của Member.
   - Tạo, phân công và sắp xếp độ ưu tiên của work item trong **Backlog** (US-3.1).
   - Lập kế hoạch, kích hoạt và đóng Sprint (US-3.4); dời việc dở dang (Rollover).
   - Thiết lập `weekly_capacity` của từng thành viên để AI phân tích quá tải.
   - Kết nối 1 repository GitHub chính của nhóm (US-5.1); yêu cầu thành viên xác nhận tài khoản GitHub qua OAuth (Mục 7.4).
   - Yêu cầu AI đề xuất Backlog, xem xét chỉnh sửa và phê duyệt áp dụng (US-5.4).
   - Chuyển trạng thái của mọi task trên Kanban.

3. **Giảng viên (Teacher):**
   - Theo dõi tiến độ Sprint, xem biểu đồ Burndown Chart và snapshot metric Work của các nhóm trong lớp phụ trách.
   - Để lại nhận xét, phản hồi (Feedback) hướng dẫn đồ án ở cấp **Project Dashboard** hoặc **Task chi tiết** (US-4.5).
   - *Quy tắc an toàn (US-4.5):* Phản hồi của Teacher tuyệt đối không tự động thay đổi trạng thái, deadline hay phân công công việc của sinh viên. Không có quyền tạo task backlog.

4. **AI Service Agent (FastAPI + Google ADK):**
   - Đọc AI Context DB riêng được cập nhật qua Kafka; không gọi context REST sang Work.
   - Chạy các agent phân rã task hoặc gợi ý backlog.
   - *Quy tắc an toàn (Mục 7.5):* Hoạt động theo cơ chế **Suggestion-only**, không tự ý tạo task hay thay đổi dữ liệu chính thức vào cơ sở dữ liệu.

5. **Outbox Worker (Celery Daemon):**
   - MVP dùng một publisher, đọc pending theo project_sequence và đợi ACK trước event kế tiếp cùng Project; không dùng nhiều poller SKIP LOCKED để hứa FIFO.
   - Xuất bản domain event ra Apache Kafka topics (`utask.work.events`).
   - Xử lý retry exponential backoff khi Kafka gặp sự cố.

---

## 1.1. Chiến lược Thiết kế Bố cục Tác nhân 2 Phía (2-Sided Actor Layout Strategy)

Để giải quyết triệt để tình trạng các đường liên kết (association lines) bị đan chéo chồng chéo làm rối mắt, toàn bộ hệ thống sơ đồ Use Case của `work-service` áp dụng mô hình **Bố trí Tác nhân 2 Phía (2-Sided Actor Architecture)** theo chuẩn PlantUML / Graphviz:

### 1.1.1. Nguyên lý Điều hướng Graphviz (`left to right direction`)
- **Tác nhân phía Trái (Left Actors - Primary / Initiators):** Khai báo trước khối `rectangle`, kết nối theo chiều thuận `LeftActor --> UC`. Graphviz sẽ xếp các tác nhân này vào Rank 0 (biên trái ngoài cùng) và mũi tên hướng sang phải đi vào Use Case.
- **Khối Use Case Trung tâm (System Boundary):** Nằm trọn vẹn trong `rectangle`, chiếm các rank ở giữa.
- **Tác nhân phía Phải (Right Actors - Supporting / Supervisors / Daemons):** Khai báo sau khối `rectangle`, kết nối theo cú pháp `UC <-- RightActor`. Vế trái là `UC` và vế phải là `RightActor` giúp Graphviz cố định tác nhân ở Rank cực phải; đồng thời ký hiệu `<--` đặt đầu mũi tên ở phía Use Case, đảm bảo mũi tên chỉ đúng hướng từ Actor đi **VÀO** Use Case (`RightActor ──> Use Case`), tạo nên bố cục đối xứng hoàn hảo 2 bên cùng trỏ vào khối Use Case trung tâm.

### 1.1.2. Phân định Vai trò Đối xứng theo Từng Sơ đồ
| Sơ đồ Use Case | Tác nhân Phía Trái (Left) | Tác nhân Phía Phải (Right) | Ý nghĩa Nghiệp vụ & Ranh giới |
| :--- | :--- | :--- | :--- |
| **Tổng thể Hệ thống** | Leader, Member | Teacher, AI Agent, Outbox Worker | Tách biệt Đội ngũ sinh viên thực thi đồ án với Giảng viên giám sát và Hệ thống phụ trợ. |
| **Phân hệ 1: Dự án & Thành viên** | Leader, Member | Teacher | Sinh viên chủ động cấu hình không gian làm việc; Giảng viên theo dõi và nhận bàn giao quyền. |
| **Phân hệ 2: Backlog & Task DAG** | Leader | Member | Phân định Quản trị Backlog (Leader) với Thực thi Phân rã Sub-task & Ràng buộc DAG (Member). |
| **Phân hệ 3: Bảng Kanban & State** | Member | Leader | Thực thi Tác nghiệp hàng ngày (Member) với Quản trị Cấu hình & Xử lý Ngoại lệ (Leader). |
| **Phân hệ 4: Sprint & Rollover** | Leader | Member, Teacher | Điều phối Chu kỳ Scrum (Leader) với Theo dõi Đo lường Vận tốc Burndown (Member & Teacher). |
| **Phân hệ 5: AI Assistant** | Leader, Member (Human) | AI Service Agent (Machine) | Thể hiện nguyên tắc **Human-in-the-loop**: Người duyệt bên trái, Máy đề xuất bên phải. |
| **Phân hệ 6: GitHub & Kiểm toán** | Leader, Member | Teacher, Outbox Worker | Nhóm đồ án đẩy code/thảo luận; Giảng viên phản hồi và Worker đồng bộ sự kiện nền. |

---

## 2. Hệ thống Sơ đồ Use Case (PlantUML Format)

### 2.1. Sơ đồ Use Case Tổng thể Hệ thống

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle
skinparam monochrome true
skinparam shadowing false
skinparam defaultFontName Arial, sans-serif
skinparam defaultFontSize 12
skinparam roundcorner 6

actor "Sinh viên (Member)" as Member
actor "Trưởng nhóm (Leader)" as Leader

rectangle "Work Service" {
  package "Phân hệ 1: Dự án & Thành viên" {
    usecase "UC01: Quản lý Dự án & Identifier" as UC_Proj
    usecase "UC02: Cấu hình Capacity & Phân vai" as UC_Member
  }

  package "Phân hệ 2: Backlog & Task Lifecycle" {
    usecase "UC03: Tạo Task Backlog (Leader Only)" as UC_Backlog
    usecase "UC04: Phân rã Sub-task (Hierarchical)" as UC_Decompose
    usecase "UC05: Phân công Công việc" as UC_Assign
    usecase "UC06: Thiết lập Quan hệ Phụ thuộc DAG" as UC_DAG
    usecase "UC07: Epic nhóm tính năng & Nhãn Phân loại" as UC_Label
  }

  package "Phân hệ 3: Bảng Kanban & Workflow State" {
    usecase "UC08: Kéo thả Kanban (rank, revision, version)" as UC_Drag
    usecase "UC09: Chuyển Trạng thái Task (Theo quyền)" as UC_State
    usecase "UC10: Đánh dấu Blocked & Ghi nguyên nhân" as UC_Block
  }

  package "Phân hệ 4: Vòng đời Sprint & Chu kỳ" {
    usecase "UC11: Lập Kế hoạch Sprint (Leader Only)" as UC_PlanSprint
    usecase "UC12: Gán Task vào Sprint (sprint_tasks)" as UC_AssignSprint
    usecase "UC13: Đóng Sprint & Chốt Closure Facts" as UC_CloseSprint
    usecase "UC14: Dời Task Dở dang sang Sprint Mới" as UC_Rollover
  }

  package "Phân hệ 5: Tương tác AI Trợ lý" {
    usecase "UC15: Đồng bộ Dữ kiện AI qua Kafka" as UC_AIContext
    usecase "UC16: Áp dụng Subtask AI đã duyệt" as UC_AIDecompose
    usecase "UC17: Duyệt Đề xuất Backlog từ AI" as UC_AIApprove
  }

  package "Phân hệ 6: Truy vết GitHub & Kiểm toán" {
    usecase "UC18: Liên kết Commit/PR từ Repo Chính" as UC_Trace
    usecase "UC19: Trao đổi Task & Feedback Giảng viên" as UC_Comment
    usecase "UC20: Ghi vết Biến động (Activity)" as UC_Audit
    usecase "UC21: Xuất bản Sự kiện Outbox ra Kafka" as UC_Outbox
    usecase "UC22: Tệp Đính kèm Task / Project" as UC_Attachment
  }
}

actor "Giảng viên (Teacher)" as Teacher
actor "AI Service Agent" as AIAgent
actor "Outbox Worker" as Worker

Leader --> UC_Proj
Leader --> UC_Attachment
Leader --> UC_Member
Leader --> UC_Backlog
Leader --> UC_Decompose
Leader --> UC_Assign
Leader --> UC_DAG
Leader --> UC_Label
Leader --> UC_Drag
Leader --> UC_State
Leader --> UC_Block
Leader --> UC_PlanSprint
Leader --> UC_AssignSprint
Leader --> UC_CloseSprint
Leader --> UC_Rollover
Leader --> UC_AIDecompose
Leader --> UC_AIApprove
Leader --> UC_Trace
Leader --> UC_Comment

Member --> UC_Decompose
Member --> UC_Label
Member --> UC_Attachment
Member --> UC_Drag
Member --> UC_State
Member --> UC_Block
Member --> UC_AIDecompose
Member --> UC_Trace
Member --> UC_Comment

' Right Connections (Arrow points into Use Case)
UC_Comment <-- Teacher
UC_Audit <-- Teacher
UC_Attachment <-- Teacher : chỉ xem/download

UC_AIContext <-- AIAgent
UC_Outbox <-- Worker

UC_Backlog ..> UC_Audit : <<include>>
UC_State ..> UC_Audit : <<include>>
UC_State ..> UC_Outbox : <<include>>
UC_Rollover ..> UC_CloseSprint : <<extend>>
UC_CloseSprint ..> UC_Outbox : <<include>>
UC_AIApprove ..> UC_Backlog : <<include>>
@enduml
```

---

### 2.2. Sơ đồ Use Case Chi tiết Phân hệ 1: Quản lý Dự án & Thành viên (Epic 2)

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle
skinparam monochrome true
skinparam shadowing false
skinparam defaultFontName Arial, sans-serif
skinparam defaultFontSize 12
skinparam roundcorner 6

' Left Actors (Initiators / Team)
actor "Trưởng nhóm (Leader)" as Leader
actor "Sinh viên (Member)" as Member

rectangle "Phân hệ 1: Dự án & Thành viên" {
  usecase "UC01.1: Khởi tạo Project & Cấp Identifier (UT)" as UC_CreateProj
  usecase "UC01.2: Cập nhật Thông tin Đề tài & Tech Stack" as UC_UpdateProj
  usecase "UC02.1: Cấu hình Weekly Capacity (Giờ/tuần)" as UC_SetCapacity
  usecase "UC02.2: Đồng bộ Leader từ Classroom" as UC_ChangeLeader
  usecase "UC02.3: Đồng bộ Member rời nhóm từ Classroom" as UC_KickMember
  usecase "UC02.4: Xem Danh sách Thành viên & Đóng góp" as UC_ViewMembers
}

' Right Actors (Supervisor)
actor "Giảng viên (Teacher)" as Teacher
actor "Classroom Service" as Classroom

' Left Connections
Leader --> UC_CreateProj
Leader --> UC_UpdateProj
Leader --> UC_SetCapacity
UC_ChangeLeader <-- Classroom
UC_KickMember <-- Classroom
Leader --> UC_ViewMembers

Member --> UC_ViewMembers

' Right Connections (Arrow points into Use Case)
UC_ViewMembers <-- Teacher

@enduml
```

---

### 2.3. Sơ đồ Use Case Chi tiết Phân hệ 2: Backlog, Task & Phụ thuộc (Epic 3, US-3.1 & US-5.5)

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle
skinparam monochrome true
skinparam shadowing false
skinparam defaultFontName Arial, sans-serif
skinparam defaultFontSize 12
skinparam roundcorner 6

' Left Actor (Backlog Governance)
actor "Trưởng nhóm (Leader)" as Leader

rectangle "Phân hệ 2: Backlog & Task Management" {
  usecase "UC03.1: Tạo Task Backlog (Leader Only - Counter)" as UC_CreateTask
  usecase "UC03.2: Chỉnh sửa Tiêu đề, Mô tả, Story Points" as UC_EditTask
  usecase "UC03.3: Phân công Thành viên (TaskAssignment)" as UC_AssignTask
  usecase "UC03.4: Xóa mềm / Lưu trữ Task" as UC_ArchiveTask
  usecase "UC04.1: Tạo Sub-task phân cấp (Hierarchical - US-5.5)" as UC_CreateSubtask
  usecase "UC06.1: Thêm Quan hệ Phụ thuộc DAG (BLOCKS...)" as UC_AddRelation
  usecase "UC06.2: Xóa Quan hệ Phụ thuộc" as UC_RemoveRelation
  usecase "UC07.1: Gán / Bỏ Nhãn Dán Phân loại (Label)" as UC_AttachLabel
  usecase "UC07.2: Quản lý Epic / Gán Task vào Epic" as UC_Epic
  usecase "UC07.3: Sửa Nội dung / Status Epic được Phụ trách" as UC_EpicContent
  usecase "UC07.4: Xem Epic của Project" as UC_ReadEpic
}

' Right Actor (Task Collaborator)
actor "Sinh viên (Member)" as Member

' Left Connections
Leader --> UC_CreateTask
Leader --> UC_EditTask
Leader --> UC_AssignTask
Leader --> UC_ArchiveTask
Leader --> UC_CreateSubtask
Leader --> UC_AddRelation
Leader --> UC_RemoveRelation
Leader --> UC_AttachLabel
Leader --> UC_EpicContent
Leader --> UC_ReadEpic

' Right Connections (Arrow points into Use Case)
UC_CreateSubtask <-- Member
UC_AddRelation <-- Member
UC_RemoveRelation <-- Member
Leader --> UC_Epic
Member --> UC_EpicContent : chỉ Epic lead ACTIVE
Member --> UC_ReadEpic
actor "Giảng viên (Teacher)" as Teacher
Teacher --> UC_ReadEpic : đúng lớp
UC_AttachLabel <-- Member
@enduml
```

---

### 2.4. Sơ đồ Use Case Chi tiết Phân hệ 3: Bảng Kanban & Workflow State Engine (US-3.2, US-3.3)

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle
skinparam monochrome true
skinparam shadowing false
skinparam defaultFontName Arial, sans-serif
skinparam defaultFontSize 12
skinparam roundcorner 6

' Left Actor (Daily Execution)
actor "Sinh viên (Member)" as Member

rectangle "Phân hệ 3: Bảng Kanban & State Engine" {
  usecase "UC08.1: Xem Bảng Kanban theo Cột Workflow" as UC_ViewKanban
  usecase "UC08.2: Lọc Task (Assignee, Priority, Deadline)" as UC_FilterKanban
  usecase "UC08.3: Kéo thả Task được giao (rank/version)" as UC_DragCard
  usecase "UC08.4: Quản lý Cột Trạng thái (Gắn StateGroup)" as UC_ManageStates
  usecase "UC09.1: Chuyển State Task của Mình (Member - US-3.3)" as UC_ChangeStateSelf
  usecase "UC09.2: Chuyển State Task Bất kỳ (Leader)" as UC_ChangeStateAny
  usecase "UC10.1: Đánh dấu Task Bị chặn & Nhập Lý do (US-3.3)" as UC_MarkBlocked
  usecase "UC10.2: Gỡ bỏ Trạng thái Bị chặn" as UC_UnmarkBlocked
}

' Right Actor (Workflow Governance & Exception Handling)
actor "Trưởng nhóm (Leader)" as Leader

' Left Connections
Member --> UC_ViewKanban
Member --> UC_FilterKanban
Member --> UC_DragCard
Member --> UC_ChangeStateSelf
Member --> UC_MarkBlocked
Member --> UC_UnmarkBlocked

' Right Connections (Arrow points into Use Case)
UC_ViewKanban <-- Leader
UC_ChangeStateAny <-- Leader
UC_MarkBlocked <-- Leader
UC_UnmarkBlocked <-- Leader
UC_ManageStates <-- Leader
@enduml
```

---

### 2.5. Sơ đồ Use Case Chi tiết Phân hệ 4: Vòng đời Sprint & Dời Chu kỳ (P1 Pilot - US-3.4)

*Ghi chú Nghiệp vụ:* Chức năng Sprint thuộc nhóm ưu tiên **Should** (PRD US-3.4 và mục 8.2 P1), được kích hoạt sau khi quy trình Kanban cơ bản đã ổn định. Giảng viên chỉ có quyền xem (Read-only) biểu đồ Burndown, tuyệt đối không có quyền can thiệp Đóng Sprint. Khi đóng Sprint, việc dở dang có thể dời sang Sprint mới hoặc đưa về Backlog.

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle
skinparam monochrome true
skinparam shadowing false
skinparam defaultFontName Arial, sans-serif
skinparam defaultFontSize 12
skinparam roundcorner 6

' Left Actor (Scrum Master / Planner)
actor "Trưởng nhóm (Leader)" as Leader

rectangle "Phân hệ 4: Sprint Lifecycle & Rollover" {
  usecase "UC11.1: Tạo Sprint Mới (Mục tiêu, Start/End Date)" as UC_CreateSprint
  usecase "UC11.2: Kích hoạt Sprint (Active Sprint duy nhất - US-3.4)" as UC_StartSprint
  usecase "UC12.1: Đưa Task vào Sprint (sprint_tasks)" as UC_AddTaskSprint
  usecase "UC12.2: Rút Task khỏi Sprint (Về Backlog)" as UC_RemoveTaskSprint
  usecase "UC13.1: Đóng Sprint & Chốt Closure Facts" as UC_CloseSprint
  usecase "UC14.1: Chuyển Task Dở dang sang Sprint Kế tiếp" as UC_RolloverIncomplete
  usecase "UC14.2: Chuyển Task Dở dang Về Lại Backlog" as UC_ReturnBacklog
  usecase "UC13.2: Xem Biểu đồ Burndown Chart & Snapshot" as UC_ViewBurndown
}

' Right Actors (Monitoring & Evaluation)
actor "Sinh viên (Member)" as Member
actor "Giảng viên (Teacher)" as Teacher

' Left Connections
Leader --> UC_CreateSprint
Leader --> UC_StartSprint
Leader --> UC_AddTaskSprint
Leader --> UC_RemoveTaskSprint
Leader --> UC_CloseSprint
Leader --> UC_ViewBurndown

' Right Connections (Arrow points into Use Case)
UC_ViewBurndown <-- Member
UC_ViewBurndown <-- Teacher

UC_RolloverIncomplete ..> UC_CloseSprint : <<extend>>
UC_ReturnBacklog ..> UC_CloseSprint : <<extend>>
@enduml
```

---

### 2.6. Phân hệ 5: Work áp dụng kết quả AI (nội bộ AI ngoài phạm vi)

User yêu cầu/xem/sửa đề xuất tại AI API thuộc nhóm AI; Work chỉ export context và apply đã duyệt. Không vẽ AI request/storage bên trong Work boundary. Các đường tích hợp là contract mục tiêu, chưa có source.

```plantuml
@startuml
left to right direction
skinparam monochrome true
skinparam shadowing false
actor "Leader / Assignee" as User
actor "Nhóm AI" as AI
rectangle "AI Service (nhóm khác sở hữu)" {
  usecase "Yêu cầu, xem và sửa đề xuất" as ReviewAI
}
rectangle "Work Service" {
  usecase "Export context Work qua Kafka" as Context
  usecase "Kiểm quyền, revision và provenance" as Validate
  usecase "Áp dụng backlog / subtask đã duyệt" as Apply
  usecase "Trả / phát bằng chứng commit" as Result
}
User --> ReviewAI
User --> Apply
AI --> Context : request async theo contract
Apply ..> Validate : <<include>>
Apply ..> Result : <<include>>
Result --> AI : event / reconcile theo contract
@enduml
```

### 2.7. Sơ đồ Use Case Chi tiết Phân hệ 6: Truy vết GitHub & Kiểm toán (US-4.1, US-4.5, US-5.1 $\rightarrow$ US-5.3)

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle
skinparam monochrome true
skinparam shadowing false
skinparam defaultFontName Arial, sans-serif
skinparam defaultFontSize 12
skinparam roundcorner 6

' Left Actors (Student Project Team)
actor "Trưởng nhóm (Leader)" as Leader
actor "Sinh viên (Member)" as Member

rectangle "Phân hệ 6: GitHub Traceability & Audit" {
  usecase "UC18.1: Kết nối Repository Chính của Nhóm (US-5.1)" as UC_ConnectRepo
  usecase "UC18.2: Gợi ý Link GitHub và xác nhận qua mã Task (US-5.2)" as UC_LinkCommit
  usecase "UC18.3: Xem Lịch sử Code & Review Status trong Task (US-5.3)" as UC_ViewGitTrace
  usecase "UC18.4: Liên kết Thủ công Commit/PR từ Giao diện (US-5.2)" as UC_ManualLinkGit
  usecase "UC19.1: Trao đổi & Mention Thành viên trong Task (US-4.1)" as UC_AddComment
  usecase "UC19.2: Giảng viên Gửi Phản hồi Feedback Hướng dẫn (US-4.5)" as UC_TeacherFeedback
  usecase "UC20.1: Xem Nhật ký Lịch sử Biến động Task (Activity)" as UC_ViewAudit
  usecase "UC21.1: Quét và Đẩy Sự kiện Outbox vào Kafka" as UC_DrainOutbox
  usecase "UC22.1: Upload / Confirm / Xóa Tệp Task hoặc Project" as UC_WriteAttachment
  usecase "UC22.2: Xem / Download Tệp đã Confirm" as UC_ReadAttachment
}

' Right Actors (External Supervisor & System Daemon)
actor "Giảng viên (Teacher)" as Teacher
actor "Outbox Worker" as Worker

' Left Connections
Leader --> UC_ConnectRepo
Leader --> UC_WriteAttachment
Leader --> UC_ReadAttachment
Leader --> UC_LinkCommit
Leader --> UC_ViewGitTrace
Leader --> UC_ManualLinkGit
Leader --> UC_AddComment
Leader --> UC_ViewAudit

Member --> UC_LinkCommit
Member --> UC_WriteAttachment
Member --> UC_ReadAttachment
Member --> UC_ViewGitTrace
Member --> UC_ManualLinkGit
Member --> UC_AddComment
Member --> UC_ViewAudit

' Right Connections (Arrow points into Use Case)
UC_ViewGitTrace <-- Teacher
UC_ReadAttachment <-- Teacher
UC_TeacherFeedback <-- Teacher
UC_ViewAudit <-- Teacher
UC_DrainOutbox <-- Worker
@enduml
```

---

## 3. Bảng Đặc tả Chi tiết các Use Case Trọng yếu

| Mã UC | Tên Use Case | Actor Chính | Tiền điều kiện | Hậu điều kiện | Luồng Sự kiện Chính (Main Flow) & Ràng buộc Nghiệp vụ |
| :---: | :--- | :---: | :--- | :--- | :--- |
| **UC03.1** | **Tạo Task trong Backlog** | Team Leader | Leader đã đăng nhập, thuộc project. | Task mới được tạo với mã `UT-X`, lưu sequence và outbox event. | 1. Leader gửi thông tin task (`title`, `description_html`, `type`, `priority`, `story_points`, `due_date`).<br>2. **Kiểm tra quyền:** Nếu không phải `LEADER` $\rightarrow$ Trả về `403 Forbidden` (US-3.1).<br>3. Mở transaction với project barrier và durable receipt.<br>4. Project.current_task_sequence UPDATE RETURNING cấp N mã trong transaction.<br>5. Tự động sinh `description_stripped = strip_tags(html)` cho AI.<br>6. Lưu `Task`, `Project.current_task_sequence`, `Activity` và `OutboxEvent` (`task.created`).<br>7. Commit transaction, lock tự giải phóng. |
| **UC04.1** | **Phân rã Sub-task** | Member phụ trách / Leader | Task cha tồn tại và thuộc project của nhóm. | Sub-task mới được tạo có `parent_id = task_cha.id`. | 1. Member phụ trách task cha hoặc Leader gửi yêu cầu tạo việc con.<br>2. Cấp phát mã `sequence_id` mới cho sub-task.<br>3. **Quy tắc US-5.5:** Task cha **không tự động đổi trạng thái** khi tạo sub-task.<br>4. Ghi Activity subject Task con (`task_id`, `verb='created'`); quan hệ cha nằm ở Task.parent_id, không có cột Activity.parent_id. |
| **UC08.3** | **Kéo thả Thẻ Kanban** | Member, Leader | Board Kanban đang mở, task thuộc cột workflow. | Rank/version/board_revision được cập nhật; rebalance có chi phí O(n). | 1. Người dùng kéo thả thẻ vào giữa thẻ $A$ và thẻ $B$.<br>2. Client gửi neighbor IDs và expected_version, server đọc rank dưới lock.<br>3. Server kiểm version/scope; rank hết khoảng thì rebalance và tăng board_revision.<br>4. Ghi Activity/Outbox cùng transaction; rebalance khi cần, cursor cũ yêu cầu refresh. |
| **UC09.1** | **Chuyển State Task của Mình** | Team Member | Member đã đăng nhập và được giao task (`assignments`). | Trạng thái task được cập nhật, event bắn ra Outbox. | 1. Member kéo thẻ task sang cột mới.<br>2. **Kiểm tra quyền US-3.3:** Backend kiểm tra `user_id in task.assignments`. Nếu task của người khác $\rightarrow$ Chặn `403 Forbidden`.<br>3. Vào COMPLETED từ nhóm khác mới gán completed_at; đổi cột cùng COMPLETED/reorder giữ mốc, reopen clear mốc và ghi Activity.<br>4. Ghi `Activity` và `OutboxEvent` (`task.status.changed`). |
| **UC10.1** | **Đánh dấu Task Bị chặn (Blocked)** | Member được giao / Leader | Task không thuộc COMPLETED/CANCELLED và project còn ghi được. | Cờ `is_blocked = true`, lưu `blocked_reason`, Kanban viền đỏ. | 1. Người phụ trách phát hiện trở ngại (phụ thuộc task khác, đợi review).<br>2. Bật cờ `is_blocked = true` và bắt buộc nhập lý do vào `blocked_reason` (US-3.3).<br>3. Thẻ trên bảng Kanban hiển thị viền đỏ cảnh báo và icon blocked.<br>4. Work tính rule công việc và phát facts để nhóm AI nhận context. |
| **UC13.1, UC14.1 & UC14.2**| **Đóng Sprint, Dời việc hoặc Trả về Backlog** | Team Leader | Sprint hiện tại đang `ACTIVE`. | Sprint cũ `COMPLETED`, chốt snapshot; xử lý việc dở dang linh hoạt. | 1. Leader kích hoạt đóng Sprint.<br>2. Chốt closure_snapshot facts cuối kỳ; Work tính/chốt metric versioned trong cùng closure_snapshot; nhóm AI có thể nhận facts để phân tích riêng.<br>3. Lọc toàn bộ các task có `StateGroup không thuộc COMPLETED/CANCELLED` qua bảng trung gian `sprint_tasks`.<br>4. **Lựa chọn nghiệp vụ linh hoạt (<<extend>>):**<br>- Nhánh A: Chuyển sang Sprint kế tiếp (`UC14.1`), tạo bản ghi `sprint_tasks` mới và cập nhật membership SprintTask hiện hành.<br>- Nhánh B: Đưa task dở dang về lại Backlog của dự án (`UC14.2`), kết thúc membership bằng ended_at/end_reason, không tạo hàng Sprint đích.<br>5. Chốt state/points/assignees trong closure_snapshot duy nhất; kết thúc membership bằng ended_at/end_reason để giữ lịch sử; Work dựng chart từ dữ kiện đã chốt và lịch sử thay đổi. |
| **UC17.1 $\rightarrow$ UC17.3**| **Trợ lý AI Đề xuất Backlog & Duyệt** | Team Leader | Project đã có mục tiêu, đề tài và tech stack. | Hàng loạt task chính thức được tạo trong database. | 1. Leader yêu cầu AI đề xuất backlog từ mô tả đồ án (US-5.4).<br>2. Nhóm AI nhận context/lưu proposal theo contract riêng $\rightarrow$ Trả về bản nháp đề xuất kèm Story Points và Acceptance Criteria.<br>3. Leader xem xét trên Modal, chỉnh sửa mức ưu tiên hoặc xóa bớt task.<br>4. Leader bấm "Chấp thuận & Áp dụng" $\rightarrow$ `work-service` thực thi atomic transaction tạo hàng loạt task có `source = 'AI_BACKLOG'`. |
| **UC18.2** | **Gợi ý GitHub qua Webhook và xác nhận liên kết** | Hệ thống (Consumer) | Webhook từ GitHub đẩy về qua `integration-service`. | Candidate PENDING hoặc metadata link CONFIRMED được cập nhật; user confirm trước khi coi link chính thức. | 1. Sinh viên commit code có kèm mã task (vd: `"feat: login UT-26"`).<br>2. Webhook đẩy về `integration-service` chuẩn hóa $\rightarrow$ Bắn Kafka event `github.activity.normalized`.<br>3. Work consumer kiểm repo/generation/version và dedup; link đã confirmed được cập nhật, task code mới chỉ tạo candidate PENDING. Member/Leader confirm mới thành official link.<br>4. **Quy tắc US-5.2:** PR merge không tự động đổi task sang Done. |
| **UC18.4** | **Liên kết Thủ công Commit/PR vào Task** | Member, Leader | Repository chính đã liên kết, task đang mở trên UI. | Bản ghi `task_github_links` được tạo sau khi xác nhận. | 1. Sinh viên hoặc Leader mở tab GitHub trong giao diện task chi tiết.<br>2. Nhập Commit SHA, số Pull Request (`#12`) hoặc tên Branch từ repository chính.<br>3. **Quy tắc US-5.2:** Sinh viên xác nhận trước khi liên kết chính thức. Hệ thống ghi nhật ký biến động `Activity`. |
| **UC19.2** | **Giảng viên Gửi Phản hồi (Feedback)** | Giảng viên phụ trách | Lớp học đang diễn ra, nhóm thuộc lớp giảng viên phụ trách. | Phản hồi được lưu trong dòng thời gian trao đổi của đồ án. | 1. Giảng viên mở Project Dashboard hoặc Task chi tiết của nhóm.<br>2. Nhập nhận xét/hướng dẫn đồ án.<br>3. **Kiểm tra quyền US-4.5:** Giảng viên chỉ gửi phản hồi cho lớp mình phụ trách. Nhận xét lưu vào `comments` có `is_teacher_feedback = true`.<br>4. **Quy tắc an toàn:** Hệ thống tuyệt đối không tự ý đổi trạng thái hay phân công task. |

---

## 4. Quyền và ownership
Các Use Case là thiết kế mục tiêu. Group kick/transfer thực hiện tại Classroom, Work chỉ đồng bộ quyền dự án. Trong sơ đồ Work, actor Classroom consumer là actor phụ trợ; Teacher không có quyền đổi Task/Sprint hoặc tự đổi ProjectMember.

Task create Leader-only; description/transition/block/subtask chỉ Assignee ACTIVE hoặc Leader, whitelist subtask không mở quyền assign/estimate/deadline. Label: Member tạo/sửa metadata nhãn và gán trên task mình phụ trách; delete Leader. Dependency: Assignee task nguồn hoặc Leader; Epic lead được sửa nội dung/status Epic được giao, không điều phối Task ngoài quyền. Đây là quyền bổ sung mục tiêu phải kiểm API/serializer thật khi triển khai.

Teacher phụ trách lớp có read/feedback/download, không upload thay member theo spec này. Admin không mặc định scope nội dung. AI chỉ đọc context nội bộ và gợi ý. Outbox worker chỉ publish, Work consumer xử lý membership/GitHub; không gộp hai vai trò kỹ thuật.

Rollover loại COMPLETED/CANCELLED; facts/metric snapshot Work khác báo cáo AI do nhóm AI giữ. Grouped board/counter/DAG/link confirmation không được gọi là hành vi nguyên trạng Plane.

---

User gửi yêu cầu/xem report qua AI API, không Work facade. Work Use Case chỉ có context export, mutation đã duyệt và bằng chứng commit; nội bộ AIDB không trong phạm vi. [Contract](../../project-service/ai-boundary-contract.md).
