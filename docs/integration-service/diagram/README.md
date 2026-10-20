# Sơ đồ Integration Service

**Trạng thái: Một phần.** Các sơ đồ phân biệt luồng account hiện có với
OAuth consent, GitHub và luồng Project còn là mục tiêu. Nguồn chuẩn về quyền
là [scope-access](../scope-access.md), về API là [api](../api.md).

| Sơ đồ | Nội dung |
| --- | --- |
| [ERD](erd.md) | Bảng GitHubAccount hiện có trong migration; không giả định schema GitHub chưa triển khai |
| [BFD](bfd.md) | Phân rã trách nhiệm hiện có và mục tiêu |
| [DFD](dfd.md) | Bearer qua Identity `/users/me`, persistence account và consent tương lai |

Sơ đồ là mô tả trạng thái theo bằng chứng, không xác nhận OAuth provider,
credential, GitHub App, webhook hay Work mutation đã chạy.
