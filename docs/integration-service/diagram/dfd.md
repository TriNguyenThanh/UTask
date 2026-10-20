# Integration Service — DFD

**Trạng thái: Một phần.** Sơ đồ trên mô tả luồng account đã có trong source;
OAuth consent và trao đổi với GitHub là mục tiêu. Không mô tả schema/token flow
chưa có. Xem [API](../api.md) và [quyền truy cập](../scope-access.md).

## Luồng API account hiện có

```mermaid
sequenceDiagram
    actor U as User / Web
    participant I as Integration
    participant ID as Identity
    participant DB as integration_db

    U->>I: GET hoặc DELETE /api/v1/github/account + Bearer
    I->>ID: GET /users/me + chuyển tiếp Bearer
    ID->>ID: Tự kiểm JWT và trạng thái phiên
    ID-->>I: success, data.id
    I->>DB: Đọc account theo user_id
    alt GET
        DB-->>I: Account hoặc không có record
        I-->>U: Account hiện tại / UNLINKED
    else DELETE
        I->>DB: Đánh dấu REVOKED, tăng version khi cần
        DB-->>I: Account đã thu hồi hoặc trạng thái hiện tại
        I-->>U: Account hiện tại
    end
```

DELETE hiện thu hồi mapping trong Integration; chưa gọi GitHub để thu hồi
token. `user_id` lấy từ Identity, không lấy từ body/query. Identity kiểm JWT
và session; Integration không gọi API mapping SocialAccount hay exchange
OAuth proof.

## Luồng mục tiêu

```mermaid
flowchart LR
    U[User / browser] -->|Bearer đã xác thực| I[Integration]
    I -->|GET /users/me + Bearer| ID[Identity]
    ID -->|data.id sau khi kiểm JWT/session| I
    I --> DB[(integration_db)]
    I -.->|M3 consent cá nhân, chưa có| GH[GitHub OAuth/provider]
    I -.->|Snapshot GET khi cần, chưa tích hợp runtime| W[Work API]
    W -->|Project/Task/membership snapshot| I
```

Consent tương lai sẽ do Integration sở hữu. Không yêu cầu Work project/leader
để liên kết account cá nhân. GitHub App/repository, webhook, đồng bộ, context
Work/AI và Kafka chưa được triển khai.

Work sở hữu Project, Task, quyền và các mutation nghiệp vụ. GET Work hiện có
cho `/projects/{id}/`, `/tasks/{id}/` và `/projects/{id}/members/` chỉ đủ cho
snapshot đọc, không bảo đảm authorization hoặc CAS cho ghi. Không có luồng
prepare/confirm hay mutation trong sơ đồ mục tiêu khi chưa có contract Work.
