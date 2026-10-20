# Kế hoạch triển khai Integration Service theo từng phần

> Yêu cầu: triển khai từng phần để giữ rõ phạm vi, quyền và dependency; mức Tiêu chuẩn do người dùng chọn.
> Trạng thái: **Thiết kế mục tiêu — chưa triển khai theo kế hoạch này**. Bằng chứng tại commit `4f5d6e74ed5c565f81625980589c796b3822f7c0`; GitNexus chậm 1 commit, không refresh vì dùng source làm căn cứ chính.
> Evidence provenance schema 2; global dirty digest `0a9c85780067d9afcd0764f307b60891e3cee927ee11eaeb5ec7826d10fd82cd`; manifest 17 đường dẫn đã sắp xếp; chỉ loại trừ `docs/plans/2026-10-15-gitnexus-plan-integration-staged-implementation.md`.

## Mục tiêu (§1)
[inferred] Hoàn thành từng luồng nhỏ có thể kiểm chứng, từ Identity liên kết GitHub đến Work dùng repository/reference thật, rồi mới đồng bộ nền, AI và UI; mỗi milestone là một nhóm PR nhỏ có điều kiện đóng/mở riêng.

## Hiện trạng (§2–3)
- [verified] Chưa có runtime Integration; chính sách/API là thiết kế mục tiêu: [tài liệu service](../integration-service/README.md), [phạm vi và quyền](../integration-service/scope-access.md).
- [verified] Work mặc định `UnavailableIntegration`; `integration_client` cấp adapter cho `select_repository` và `manual_link` ([adapter:130](../../apps/work-service/infrastructure/integration.py)). Work kiểm quyền/generation lại sau provider call ([repositories.py:79](../../apps/work-service/apps/integrations/services/repositories.py), [links.py:197](../../apps/work-service/apps/integrations/services/links.py)).
- [verified] Identity đã có client exchange proof nhưng chưa cho Integration gọi session-status ([proof client:19](../../apps/identity-service/authentication/adapters/github_identity_proof.py), [allowlist:17](../../apps/identity-service/authentication/views/internal.py)). Mapping danh tính chưa đủ chứng minh quyền GitHub user.
- [verified] CI discovery yêu cầu manifest/lockfile/Dockerfile; local gateway còn chờ Integration healthy, staging dùng profile ([discovery:14](../../scripts/discover_services.py), [local Compose:165](../../docker-compose.yml), [staging:171](../../docker-compose.staging.yml)).

## Phát hiện ảnh hưởng (§4–5)
- [graph] `context(integration_client)` và `impact(integration_client, upstream, maxDepth:1)`: `risk: LOW`, `epistemic: exact`, đúng hai direct caller `select_repository`/`manual_link`; kiểm hồi quy cả hai ở M5. Graph cũ nên danh sách không thay kiểm source lúc thực thi.
- [graph] `pdg_query(controls, repositories.py)` trả `no PDG layer`; không suy ra cạnh PDG từ source. Các ràng buộc thứ tự ở trên là source-verified; chỉ chạy `analyze --index-only --pdg` nếu bước triển khai cần phân tích sâu hơn.

## Phạm vi thay đổi (§6)
[inferred] Mỗi thư mục Integration dưới đây là **đường dẫn dự kiến tạo mới**, không phải code đang có. API/permission có người phụ trách duy nhất; Work vẫn sở hữu TaskGitHubLink, Identity sở hữu OAuth mapping, Integration chỉ đọc GitHub. Không tạo FK xuyên service, không dùng PAT làm kiến trúc chính.

## Thứ tự triển khai và tiêu chí nghiệm thu (§7)
| Phần / phụ thuộc | Công việc và phạm vi file | Kiểm thử và điều kiện qua bước |
| --- | --- | --- |
| **M0 — Chốt hợp đồng**, bắt đầu | Chủ trì backend Integration + chủ service liên quan: cập nhật `docs/integration-service/{api,scope-access}.md`; chốt action/target và actor delegation Work, session Identity, OAuth App/user consent, token lifecycle, generation/idempotency, reconcile khi Work từ chối sau provider call, schema sự kiện đầu tiên. Chỉ thêm artifact `contracts/api/` và `contracts/events/` sau khi thống nhất, có ví dụ/validator; chia contract theo milestone, không tạo placeholder. | Đối chiếu proof client Identity, hai Work fact/port và AI adapter; ma trận user/caller có cả ca được phép/từ chối. **Gate:** cách chứng minh quyền chính GitHub user đã xác định; không coi OAuth mapping/App token là đủ. |
| **M1 — Khung chạy được**, sau M0 | Backend Integration: `apps/integration-service/{pyproject.toml,uv.lock,Dockerfile,manage.py,config/,common/,tests/}` và README app trỏ docs chuẩn. Infra phụ trách Compose, env, role/credential PostgreSQL riêng Integration, migration runner, healthcheck và cấu hình CI discovery/test env. Chưa mở API nghiệp vụ. | Unit health/config gồm thiếu config; Django check, migration check, DB role không đọc DB khác, build image, regression discovery/staging. **Gate:** CI tự nhận service và khởi động sạch; không thêm dependency vào backend nghiệp vụ chưa có. |
| **M2 — Nền xác thực và phân quyền**, sau M1 | Integration `common/`, `infrastructure/service_clients/`; Work thêm internal API kiểm **action + target + actor** bằng quyền của Work, không gọi vòng Integration; Identity bổ sung caller/session contract đúng lựa chọn M0. Infra chặn internal Integration tại Nginx và route con; key riêng Identity/Work/AI. | Thiếu/sai key, key nhầm caller, revoked session, member/teacher/admin không đủ scope, Work timeout → từ chối; internal route không lộ gateway. **Gate:** mọi endpoint khai báo quyền trước khi thêm handler nghiệp vụ, không có fallback allow. |
| **M3 — GitHub adapter và OAuth proof**, sau M2 | Integration `infrastructure/github/`, `apps/identity_proofs/` và lưu bí mật có mã hóa/rotation theo M0; hiện thực exchange tương thích `GitHubIdentityProofClient`. Tách proof danh tính với user authorization dùng liệt kê repo; kiểm mapping Identity và cơ chế revoke/re-consent. Không log code/verifier/token. | Provider fake: success, timeout, code lỗi, binding/expiry sai, retry/replay, đổi GitHub user, unlink, token hết hạn; contract test với Identity thật trong môi trường test. **Gate:** có thể thử riêng luồng liên kết GitHub qua Identity; chưa mở chức năng Project. |
| **M4 — Installation và webhook quyền**, sau M3 | Integration `apps/installations/`, `apps/repositories/`, `apps/webhooks/`, nền `apps/messaging/`; model/migration tối thiểu Installation/Repository, state cài App, delivery inbox/outbox. Start/callback/list dựa quyền Work + GitHub user. Nhận webhook signed installation/repository, lưu bền vững và xử lý/retry bằng worker/dispatcher riêng; thêm Redis và process metadata trong Compose. | Callback sai state/replay/mất quyền; callback thành công **không** tạo ProjectConnection; user A không xem repo B; signature sai, delivery trùng, crash sau nhận và resume, suspend/uninstall/repo access removed. **Gate:** biết thu hồi quyền và không dùng dữ liệu cũ để tiếp tục cấp quyền; outbox schema đã chốt, chưa bật consumer mới. |
| **M5 — Work kết nối và link thủ công**, sau M4 | Integration ProjectConnection + API chọn/đọc/ngắt/verify; Work `infrastructure/integration.py`, `apps/integrations/{services,views,serializers}/`, settings/env thêm HTTP adapter và route ngắt còn thiếu. Cài **cả hai** port chọn repo/xác minh ref trước bật adapter; giữ guard trước/sau HTTP, không giữ DB lock xuyên HTTP. DB migration chỉ cho dữ liệu milestone này. | Leader chọn được, member bị chặn; branch/commit/PR verified tạo link qua Work; duplicate operation, generation cũ, đổi membership giữa HTTP, response mất hoặc Work từ chối sau Integration commit → reconcile đúng. Ngắt được khi App đã gỡ, không ảnh hưởng Project khác. **Gate:** luồng backend từ đầu đến cuối trên repo test; chưa bulk sync/AI; giữ công tắc adapter để quay về unavailable. |
| **M6 — Đồng bộ đầy đủ và sự kiện**, sau M5 | Integration `apps/github_data/`, SyncJob, dispatcher/worker, retry/rate limit, pagination/cursor theo repo, publisher outbox; mở lần lượt commit/branch/PR rồi issue. Work consumer cập nhật connection/account facts và link candidates theo contract M0; Identity linked/unlinked cập nhật credential/mapping theo đúng nguồn sở hữu, không xác nhận link Task tự động. Infra thêm process publisher/consumer và Kafka ACL cần thiết. | DB/Redis/Kafka down, mất ACK, delivery/job/event lặp, event đảo thứ tự, worker chết, concurrent generation, App revoked giữa các trang; không mất job/event và không ghi lặp. **Gate:** sync initial/incremental, retry hữu hạn, trạng thái lỗi cuối, Work projection reconcile được; chỉ `202` sau lưu bền vững. |
| **M7 — Context AI**, sau M6 | Integration API `github-activity` chỉ read, lọc user/project/time; AI cấu hình URL và mapping domain đã có, không cho agent gọi HTTP tùy ý; cập nhật docs/contract context. Notification chỉ bật subscription khi có use case/schema, không là dependency bắt buộc của M7. | AI key không gọi được command/OAuth/list; sai project, user rời, teacher hết scope, stale/missing/partial, pagination/giới hạn payload, không lộ secret; regression `apps/ai-service/tests/test_context.py`. **Gate:** AI dùng context thật ở môi trường test, Integration lỗi không chặn Work/auth. |
| **M8 — Giao diện người dùng**, sau M5 và M6; phần AI UI sau M7 | Frontend phụ trách `apps/web/src/features/` và API client/test cùng luồng: liên kết tài khoản qua Identity; leader cài App/chọn repo/đồng bộ/ngắt qua đúng service; member thao tác link Task qua Work; teacher chỉ xem. Tách từng PR giao diện theo hành vi, không bật đồng loạt các endpoint chưa đạt gate. | Component/API integration: loading/error/empty, double click, conflict, expired session, mất quyền, job failed/retry; E2E ít nhất leader/member/teacher/outsider. **Gate:** một người dùng đi trọn luồng, refresh đọc được trạng thái; UI không là nơi duy nhất enforce quyền. |
| **M9 — Nghiệm thu và phát hành**, sau M8 và M7 nếu bật AI | Infra + reviewer: chạy local CI/image/Compose; staging migrations, health, credential/ACL, worker/publisher monitoring, replay và cleanup theo retention. Cập nhật docs API/schema/ERD theo source/test. Bật tính năng lần lượt trên repo test → nhóm thử → phạm vi dự kiến sau nghiệm thu; triển khai thực tế là task riêng. | E2E nhiều service, contract compatibility, recovery DB/broker/worker, revoke/install/unlink, kiểm dữ liệu nhạy cảm. **Gate:** mọi prerequisite đã đạt, rollback diễn tập; tắt feature/adapter trước, giữ dữ liệu/migration tương thích và không xóa outbox/job chưa xử lý. |

[inferred] Đường găng: M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7/M8 → M9. M7 và UI không dùng AI ở M8 có thể song song sau M6; không mở UI chỉ vì mock chạy được. MVP backend đầu tiên là M5; nhóm thử người dùng đi qua M8, hoàn tất độ bền/thu hồi quyền ở M6 trước đó.
[inferred] Mỗi milestone chia thành PR model/migration → service/API+test → adapter/integration+docs khi cần; **mỗi PR vẫn có test tương ứng và chạy được**, không dồn unit test sang phần sau. Một Integration owner quản lý contract/lockfile/migration của service; Work, Identity, AI, frontend, infra có owner riêng, không sửa cùng file song song. Không khóa lịch theo số ngày khi chưa có vận tốc nhóm.

## Chiến lược kiểm thử (§8)
- [verified] Hồi quy đã có: [Work repository race:91](../../apps/work-service/tests/integration/test_github_api.py), [Identity OAuth mocked exchange:120](../../apps/identity-service/tests/test_oauth_adapters.py), [AI context:41](../../apps/ai-service/tests/test_context.py). Bổ sung transport/contract test thật, không thay các ca guard bằng mock chỉ trả success.
- [inferred] Integration thêm unit, API/contract, PostgreSQL constraints/concurrency, Redis worker recovery, Kafka publish/consume và E2E theo từng hàng M1–M9; fixture GitHub là mặc định CI, repo test GitHub thật chỉ chạy external/E2E có credential riêng. Không chạy bộ test ghi đồng thời trên cùng database; credential test không dùng production.
- [verified] Lệnh hiện có: tại root `python scripts/ci_local.py --skip-images` (có uv/Docker và môi trường test), đầy đủ bỏ `--skip-images`; workflow Python chạy `uv sync --all-groups --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check`, `uv run python manage.py makemigrations --check --dry-run`, `uv run pytest`, `docker build ...` ([workflow:78](../../.github/workflows/python-service.yml)). Chạy tại từng service với settings/DB test do CI discovery cấp; Integration chỉ có các lệnh này sau M1, không chạy với DB nghiệp vụ.
- [verified] Frontend: `pnpm -C apps/web lint`, `pnpm -C apps/web test`, `pnpm -C apps/web build` theo [package.json:7](../../apps/web/package.json). Khi sửa chức năng phải viết/cập nhật unit test success và lỗi/biên cùng PR; áp dụng Django/Postgres/React skill đúng phạm vi khi thực thi.

## Ngữ cảnh triển khai (§11)
```json
{
  "implementation_context": {
    "task_summary": "Triển khai Integration Service theo M0–M9 với gate quyền, contract, test và rollout; phiên hiện tại chỉ lập kế hoạch Standard.",
    "evidence_provenance": {
      "schema_version": 2,
      "head_commit": "4f5d6e74ed5c565f81625980589c796b3822f7c0",
      "generated_plan_path": "docs/plans/2026-10-15-gitnexus-plan-integration-staged-implementation.md",
      "global_dirty_digest": {
        "algorithm": "sha256",
        "canonicalization": "gitnexus-evidence-provenance-v2 NUL-framed UTF-8 records",
        "value": "0a9c85780067d9afcd0764f307b60891e3cee927ee11eaeb5ec7826d10fd82cd"
      },
      "cited_path_manifest": [
        {
          "path": ".github/workflows/python-service.yml",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:f380337967b600a4bea407e650fcd7d409752ab77ad52d0890f510aec02d47e3",
          "index_digest": "sha256:f380337967b600a4bea407e650fcd7d409752ab77ad52d0890f510aec02d47e3",
          "worktree_digest": "sha256:f380337967b600a4bea407e650fcd7d409752ab77ad52d0890f510aec02d47e3",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/ai-service/tests/test_context.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:0920eddce1ded22ac9a37e3acd219c484f5cb28b6ef4354048ed75725c8ef315",
          "index_digest": "sha256:0920eddce1ded22ac9a37e3acd219c484f5cb28b6ef4354048ed75725c8ef315",
          "worktree_digest": "sha256:0920eddce1ded22ac9a37e3acd219c484f5cb28b6ef4354048ed75725c8ef315",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/identity-service/authentication/adapters/github_identity_proof.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:8849d3a0287f303aea1bbd615b5ed2f94abc37faacba0b93eb4572d8fe7105de",
          "index_digest": "sha256:8849d3a0287f303aea1bbd615b5ed2f94abc37faacba0b93eb4572d8fe7105de",
          "worktree_digest": "sha256:8849d3a0287f303aea1bbd615b5ed2f94abc37faacba0b93eb4572d8fe7105de",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/identity-service/authentication/views/internal.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:92db01ecc6a8e129e849bac73e1fe2ba9842995468f0f6b279c805c11a69b5bc",
          "index_digest": "sha256:92db01ecc6a8e129e849bac73e1fe2ba9842995468f0f6b279c805c11a69b5bc",
          "worktree_digest": "sha256:92db01ecc6a8e129e849bac73e1fe2ba9842995468f0f6b279c805c11a69b5bc",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/identity-service/tests/test_oauth_adapters.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:4b845c8544ff0b73f2eb68472d505bf5ce9d4b85a508c7fd05871ceec0eee228",
          "index_digest": "sha256:4b845c8544ff0b73f2eb68472d505bf5ce9d4b85a508c7fd05871ceec0eee228",
          "worktree_digest": "sha256:4b845c8544ff0b73f2eb68472d505bf5ce9d4b85a508c7fd05871ceec0eee228",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/web/package.json",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:771d8ddb6c5f861387431a64f9b51793f4babf0bf8159077754a131bc6bc0028",
          "index_digest": "sha256:771d8ddb6c5f861387431a64f9b51793f4babf0bf8159077754a131bc6bc0028",
          "worktree_digest": "sha256:771d8ddb6c5f861387431a64f9b51793f4babf0bf8159077754a131bc6bc0028",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/work-service/apps/integrations/services/links.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:6cb9b091ef0bd445b4e297ba0637165dab90115be9ceeed476344de0ccc3777b",
          "index_digest": "sha256:6cb9b091ef0bd445b4e297ba0637165dab90115be9ceeed476344de0ccc3777b",
          "worktree_digest": "sha256:6cb9b091ef0bd445b4e297ba0637165dab90115be9ceeed476344de0ccc3777b",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/work-service/apps/integrations/services/repositories.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:059a93ff5854a8a2cd55a3a0a88647f41505f53f475d714704b2b2c225d4e2bd",
          "index_digest": "sha256:059a93ff5854a8a2cd55a3a0a88647f41505f53f475d714704b2b2c225d4e2bd",
          "worktree_digest": "sha256:059a93ff5854a8a2cd55a3a0a88647f41505f53f475d714704b2b2c225d4e2bd",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/work-service/infrastructure/integration.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:ed5d323d77031a93bfda41cc55fd7e8018b8318a53b007af6b78548965a6befc",
          "index_digest": "sha256:ed5d323d77031a93bfda41cc55fd7e8018b8318a53b007af6b78548965a6befc",
          "worktree_digest": "sha256:ed5d323d77031a93bfda41cc55fd7e8018b8318a53b007af6b78548965a6befc",
          "untracked_digest": "absent"
        },
        {
          "path": "apps/work-service/tests/integration/test_github_api.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:9b1a03136d62c79b6ce72334571e2b82fde1ecf7747b59ff3afae16a10f656ec",
          "index_digest": "sha256:9b1a03136d62c79b6ce72334571e2b82fde1ecf7747b59ff3afae16a10f656ec",
          "worktree_digest": "sha256:9b1a03136d62c79b6ce72334571e2b82fde1ecf7747b59ff3afae16a10f656ec",
          "untracked_digest": "absent"
        },
        {
          "path": "docker-compose.staging.yml",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:a4b4f00be889d5c117868f0a48ea35c1ee041015faceab211f3fccd05c5cf604",
          "index_digest": "sha256:a4b4f00be889d5c117868f0a48ea35c1ee041015faceab211f3fccd05c5cf604",
          "worktree_digest": "sha256:a4b4f00be889d5c117868f0a48ea35c1ee041015faceab211f3fccd05c5cf604",
          "untracked_digest": "absent"
        },
        {
          "path": "docker-compose.yml",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:a158b08be7ef5ef6988bfbd920eb9a3ea6ee016bca12ca40767bd92a14dbead8",
          "index_digest": "sha256:a158b08be7ef5ef6988bfbd920eb9a3ea6ee016bca12ca40767bd92a14dbead8",
          "worktree_digest": "sha256:a158b08be7ef5ef6988bfbd920eb9a3ea6ee016bca12ca40767bd92a14dbead8",
          "untracked_digest": "absent"
        },
        {
          "path": "docs/integration-service/README.md",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:d990c7703e5e97a7da1aa80a92cd36d9163c9471ceb9bc687825fbc5c3a13641",
          "index_digest": "sha256:d990c7703e5e97a7da1aa80a92cd36d9163c9471ceb9bc687825fbc5c3a13641",
          "worktree_digest": "sha256:d990c7703e5e97a7da1aa80a92cd36d9163c9471ceb9bc687825fbc5c3a13641",
          "untracked_digest": "absent"
        },
        {
          "path": "docs/integration-service/scope-access.md",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:de243efe56423fd7ce06f2aae8bb1b48e1eb987df4eea8a2807b270c8ae5f869",
          "index_digest": "sha256:de243efe56423fd7ce06f2aae8bb1b48e1eb987df4eea8a2807b270c8ae5f869",
          "worktree_digest": "sha256:de243efe56423fd7ce06f2aae8bb1b48e1eb987df4eea8a2807b270c8ae5f869",
          "untracked_digest": "absent"
        },
        {
          "path": "infra/nginx/nginx.conf",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:837db81ef3f38f754583e13e8ae89dc0eb079aad6d4be955eab3563b5b81efb4",
          "index_digest": "sha256:837db81ef3f38f754583e13e8ae89dc0eb079aad6d4be955eab3563b5b81efb4",
          "worktree_digest": "sha256:837db81ef3f38f754583e13e8ae89dc0eb079aad6d4be955eab3563b5b81efb4",
          "untracked_digest": "absent"
        },
        {
          "path": "scripts/ci_local.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:3f80621351d1321b65fefbdb54c9fcfdd51b966f2f9c65c03291ec032e375e94",
          "index_digest": "sha256:3f80621351d1321b65fefbdb54c9fcfdd51b966f2f9c65c03291ec032e375e94",
          "worktree_digest": "sha256:3f80621351d1321b65fefbdb54c9fcfdd51b966f2f9c65c03291ec032e375e94",
          "untracked_digest": "absent"
        },
        {
          "path": "scripts/discover_services.py",
          "object_kind": {
            "head": "regular",
            "index": "regular",
            "worktree": "regular",
            "untracked": "absent"
          },
          "state": "clean",
          "rename_from": null,
          "rename_to": null,
          "head_digest": "sha256:556329b093c694c42d5fa0878e1d7faa9842aa6658001a13cc3f04194884c8ac",
          "index_digest": "sha256:556329b093c694c42d5fa0878e1d7faa9842aa6658001a13cc3f04194884c8ac",
          "worktree_digest": "sha256:556329b093c694c42d5fa0878e1d7faa9842aa6658001a13cc3f04194884c8ac",
          "untracked_digest": "absent"
        }
      ]
    },
    "files_to_modify": [
      {
        "file": "docs/integration-service/{api,scope-access,README}.md",
        "symbols": [],
        "intended_change": "M0 chốt hợp đồng, cập nhật theo source/test từng milestone; không sửa trong phiên planning."
      },
      {
        "file": "contracts/{api,events}/",
        "symbols": [],
        "intended_change": "Artifact mới sau thống nhất contract từng milestone, không placeholder."
      },
      {
        "file": "apps/integration-service/",
        "symbols": [],
        "intended_change": "Code/config/tests/migrations mới theo M1–M7; tên module theo README, không tạo toàn ERD ngay."
      },
      {
        "file": "apps/work-service/infrastructure/integration.py",
        "symbols": [
          "integration_client",
          "ConnectionFact",
          "ReferenceFact"
        ],
        "intended_change": "M5 thêm HTTP adapter tương thích cả hai port, giữ validation; giữ cấu hình unavailable để tắt chức năng."
      },
      {
        "file": "apps/work-service/apps/integrations/{services,views,serializers}/",
        "symbols": [
          "select_repository",
          "manual_link"
        ],
        "intended_change": "M2 action/target permission endpoint ở Work theo contract M0; M5 route ngắt, giữ guard/CAS và reconcile; M6 consumer chuẩn hóa facts, không tự xác nhận Task link."
      },
      {
        "file": "apps/identity-service/authentication/{views/internal.py,adapters/github_identity_proof.py}",
        "symbols": [
          "GitHubIdentityProofClient.exchange_identity"
        ],
        "intended_change": "M2 session verification caller contract; M3 giữ proof payload, chỉ sửa client nếu contract tương thích đã chốt, không bắt Identity gọi GitHub."
      },
      {
        "file": "apps/ai-service/src/",
        "symbols": [],
        "intended_change": "M7 mapping/config github_activity phù hợp endpoint thực, caller permission read-only; không sửa pipeline nếu adapter đủ."
      },
      {
        "file": "apps/web/src/features/",
        "symbols": [],
        "intended_change": "M8 luồng UI theo vai trò và đúng service, API/component/E2E tests."
      },
      {
        "file": "docker-compose*.yml; infra/env/; infra/postgres/; infra/nginx/nginx.conf; scripts/tests/",
        "symbols": [],
        "intended_change": "Infra owner thêm metadata CI/runtime, riêng DB credential, gateway block, worker/dispatcher/publisher và hồi quy; không hardcode thêm workflow nếu discovery đủ."
      }
    ],
    "tests": [
      {
        "file": "apps/integration-service/tests/ (tạo mới)",
        "scenarios": [
          "Key Identity/Work/AI đúng action -> cho phép; key nhầm caller/thiếu -> từ chối",
          "User thiếu scope/phiên revoked -> cấm; Work unavailable -> fail closed",
          "OAuth code hợp lệ -> proof đúng binding; replay/expired/mismatch -> lỗi và không lộ credential",
          "Callback App thành công -> chỉ installation; user A list -> không lộ private repo B",
          "Webhook signed -> durable receipt; duplicate/crash -> retry không lặp; revoked App -> ngừng đọc",
          "Concurrent generation/lost response -> idempotent reconcile; DB rollback -> không event; Kafka ACK mất -> consumer không lặp",
          "AI project context -> metadata đúng phạm vi; stale/missing/oversized/secret -> xử lý theo contract"
        ]
      },
      {
        "file": "apps/work-service/tests/integration/test_github_api.py",
        "scenarios": [
          "Giữ membership/generation race guards khi thay fake bằng HTTP transport",
          "Disconnect khi App removed -> Work cho leader còn quyền, không tác động project khác",
          "Integration commit rồi Work reject -> không bypass quyền bằng event, có reconcile hữu hạn"
        ]
      },
      {
        "file": "apps/work-service/tests/unit/test_integration_facts.py",
        "scenarios": [
          "JSON response -> đúng fact; sai project/operation/ref/version -> từ chối"
        ]
      },
      {
        "file": "apps/identity-service/tests/test_oauth_adapters.py",
        "scenarios": [
          "Proof server contract -> client hiện có chấp nhận; expiry/binding/provider lỗi -> 503 phía Identity"
        ]
      },
      {
        "file": "apps/ai-service/tests/test_context.py",
        "scenarios": [
          "github_activity adapter -> đúng project và freshness; thiếu cấu hình/quyền -> từ chối; không lọt secret"
        ]
      },
      {
        "file": "scripts/tests/; apps/web/src/ (test thêm đúng component/luồng)",
        "scenarios": [
          "Service discovery/Compose/gateway -> không lộ internal; bootstrap có manifest hợp lệ -> CI nhận",
          "Leader flow và member/teacher view -> đúng UI; API 403/409/job failed -> trạng thái rõ, refresh giữ kết quả"
        ]
      }
    ],
    "verification_commands": [
      "python scripts/ci_local.py --skip-images",
      "python scripts/ci_local.py",
      "cd apps/integration-service && uv sync --all-groups --locked",
      "cd apps/integration-service && uv run ruff check .",
      "cd apps/integration-service && uv run ruff format --check .",
      "cd apps/integration-service && uv run python manage.py check",
      "cd apps/integration-service && uv run python manage.py makemigrations --check --dry-run",
      "cd apps/integration-service && uv run pytest",
      "pnpm -C apps/web lint",
      "pnpm -C apps/web test",
      "pnpm -C apps/web build"
    ],
    "assumptions": [
      "Kiểm scope-access.md ở M0: GitHub read-only, Work owns TaskGitHubLink và Progress, chưa link Issue qua Work.",
      "Lệnh uv cho Integration chỉ chạy sau M1 tạo project; kiểm workflow/discovery test_env để dùng settings và DB test riêng; full local CI cần uv và Docker.",
      "Graph cũ 1 commit, no PDG layer; khi thực thi kiểm current HEAD/dirty provenance và symbol impact, dùng source nếu không phân giải."
    ],
    "open_questions": [
      "M0 chọn registration và credential cho GitHub App user authorization so với OAuth Identity; lưu/refresh/revoke/consent và binding provider user.",
      "M0 chốt action/target permission API và actor delegation; Integration dùng session-status hay cơ chế xác minh phiên khác đã duyệt.",
      "M0 chốt version/idempotency/reconcile khi Integration đã commit nhưng Work từ chối sau HTTP; không dùng distributed DB transaction.",
      "M0/M6 chốt event envelope/names/subscriptions, replay/version, retention/ACL và chính sách dữ liệu lịch sử sau revoke.",
      "M9 điều kiện staging/credential và bật cho nhóm thử; chưa cam kết lịch hay triển khai external trong phiên planning."
    ],
    "avoid": [
      "Không khám phá lại toàn repo; bắt đầu bằng evidence manifest và chỉ kiểm phần đã đổi.",
      "Không gọi GitHub từ Work/Identity/AI hoặc đọc DB service khác.",
      "Không coi App token, mapping GitHub user hay role SYSTEM_ADMIN là đủ để cấp quyền Project/repo.",
      "Không đổi guard/CAS của select_repository/manual_link để làm E2E success giả.",
      "Không mở public endpoint trước permission/revocation gate; không dồn unit tests sang milestone sau.",
      "Không tạo skeleton contract giả, migrate toàn ERD ngay, sửa cùng lockfile/migration/contract song song hoặc deploy trong task lập kế hoạch."
    ]
  }
}
```

## Giả định và câu hỏi cần chốt (§12)
- [assumed] Giai đoạn đầu GitHub read-only; chưa có ngày phát hành hoặc yêu cầu ghi ngược GitHub. M0 đối chiếu lại `scope-access.md` với sản phẩm; link Issue, điểm/contribution tổng hợp và Notification đặc thù để sau khi có use case.
- [inferred] Quyết định M0 bắt buộc: cùng hay khác registration cho OAuth Identity/GitHub App user authorization; ai giữ/refresh/revoke credential user; thời hạn proof/state/operation, response lost retry; contract Work action/target/session; event envelope/consumer và reconcile khi hai service commit lệch nhau. Ghi kết luận cụ thể trước mở API phụ thuộc, không dùng placeholder để vượt gate.
- [graph] Graph chậm 1 commit, PDG không có; source được kiểm tại HEAD trên. Bước thực thi phải chạy impact cho từng symbol sẽ sửa và `detect_changes` trước commit; HIGH/CRITICAL phải báo, UNKNOWN phải kiểm source, không dùng kế hoạch thay kiểm thực tế.

## Điều kiện hoàn tất (§13)
[inferred] M0–M9 có bằng chứng test/check và trạng thái riêng; không đánh dấu service hoàn tất khi chỉ có schema/health/mock. User chỉ truy cập dữ liệu được phép, callback không tự nối Project, AI read-only, Work giữ link Task/tiến độ; không mất job/event khi retry và không vượt generation/quyền đã thu hồi. Docs/contract khớp source; CI/lint/format/test/build phù hợp đạt. Phiên này chỉ xuất kế hoạch, chưa sửa production code hoặc chạy test runtime.
