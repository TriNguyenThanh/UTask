<div align="center">

# UTask

### AI-Powered Agile Project Management Platform

**Quản lý dự án Scrum/Agile kết hợp AI để phân tích workload, rủi ro Sprint và hỗ trợ phân công công việc.**

![Next.js](https://img.shields.io/badge/Next.js-Frontend-black)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-336791)
![Google ADK](https://img.shields.io/badge/Google_ADK-AI_Agent-4285F4)
![Gemini](https://img.shields.io/badge/Gemini-AI-8E75B2)
![Docker](https://img.shields.io/badge/Docker-Deployment-2496ED)

</div>

---

## ✨ Tổng quan

**UTask** là nền tảng quản lý dự án CNTT dành cho **sinh viên và giảng viên**, hỗ trợ tổ chức công việc theo mô hình **Scrum/Agile**.

Ngoài các chức năng quản lý Project, Backlog, Sprint và Kanban, hệ thống tích hợp **AI Core** để phân tích dữ liệu dự án và đưa ra các khuyến nghị hỗ trợ nhóm trong quá trình làm việc.

---

## 🎯 Chức năng chính

| Module                | Chức năng                              |
| --------------------- | -------------------------------------- |
| 📁 Project Management | Quản lý Project, thành viên và Task    |
| 📋 Backlog            | Quản lý Product Backlog và Story Point |
| 🏃 Sprint             | Lập kế hoạch và theo dõi Sprint        |
| 🗂 Kanban Board       | Theo dõi trạng thái công việc          |
| 🐙 GitHub Integration | Thu thập commit và contributor         |
| 🤖 AI Core            | Phân tích và hỗ trợ ra quyết định      |

---

## 🤖 AI Core

AI Core tập trung vào **4 bài toán chính**:

### 📊 Workload Analysis

Phân tích khối lượng công việc của từng thành viên dựa trên:

`Story Point` • `Deadline` • `Capacity`

### ⚠️ Sprint Risk Assessment

Phát hiện nguy cơ Sprint bị trễ hoặc không hoàn thành mục tiêu.

### 👤 Task Assignment Recommendation

Đề xuất thành viên phù hợp với Task dựa trên:

`Workload` • `Skill` • `Deadline`

### ❤️ Project Health Assessment

Tổng hợp các chỉ số để đánh giá tình trạng tổng thể của Project và đưa ra khuyến nghị.

> **Human-in-the-loop:** AI chỉ phân tích và đề xuất, quyết định cuối cùng vẫn thuộc về người dùng.

---

## 🛠 Tech Stack

| Layer           | Technology       |
| --------------- | ---------------- |
| **Frontend**    | Next.js          |
| **Backend**     | Python · FastAPI |
| **Database**    | PostgreSQL       |
| **AI Agent**    | Google ADK       |
| **LLM**         | Gemini API       |
| **Validation**  | Pydantic         |
| **Integration** | GitHub API       |
| **Testing**     | pytest           |
| **Deployment**  | Docker           |

---

## 🏗 System Architecture

```text
┌──────────────────────────┐
│        Next.js           │
│        Frontend          │
└────────────┬─────────────┘
             │ REST API
             ▼
┌──────────────────────────┐
│         FastAPI          │
│     Application API      │
└────────────┬─────────────┘
             │
       ┌─────┴──────────────┐
       │                    │
       ▼                    ▼
┌──────────────┐     ┌──────────────┐
│ PostgreSQL   │     │   AI Core    │
│   Database   │     │   FastAPI    │
└──────────────┘     └──────┬───────┘
                            │
                     ┌──────┴───────┐
                     │              │
                     ▼              ▼
               ┌───────────┐  ┌───────────┐
               │Google ADK │  │Gemini API │
               └───────────┘  └───────────┘
```

---

## 📁 Project Structure

```text
utask/
│
├── apps/
│   ├── web/                 # Next.js Frontend
│   └── api/                 # FastAPI Backend
│
├── services/
│   └── ai-core/
│       ├── app/
│       │   ├── agents/      # AI Agents
│       │   ├── domain/      # Business logic
│       │   ├── schemas/     # Pydantic schemas
│       │   └── tools/       # Agent tools
│       │
│       ├── datasets/        # Mock & evaluation data
│       └── tests/           # AI Core tests
│
├── docs/                    # Project documentation
├── docker-compose.yml
└── README.md
```

---

## 💡 Ý tưởng chính

UTask hướng đến việc kết hợp **quản lý dự án Agile truyền thống** với **AI**, giúp nhóm:

- Theo dõi tiến độ dễ dàng hơn.
- Phát hiện sớm rủi ro của Sprint.
- Nhận biết thành viên đang quá tải.
- Hỗ trợ phân công Task phù hợp.
- Đánh giá nhanh tình trạng tổng thể của Project.

---

<div align="center">

### UTask

**Manage smarter · Detect risks earlier · Build better together**

</div>
