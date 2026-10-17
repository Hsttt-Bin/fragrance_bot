# 雾歇香薰 · AI 客服项目

## 项目结构

- `website/`：前端，含 `backend/`（FastAPI + SSE 后端）
- `knowledge_base/`：RAG 检索模块（改写 / 检索 / 精排 / 生成）
- `kb_data/`：FAISS 索引与 chunks
- `spec/`：需求与改动状态管理（见下方约定）

## 硬性约束

1. `knowledge_base/` 是核心 RAG 模块，默认不修改其下任何 Python 文件；如需修改，必须先征得用户明确授权。
2. API Key 一律从环境变量读取，不硬编码在前端或后端代码里。
3. 不在 `website/` 前端文件中出现任何密钥。

## spec 状态管理

- 每个功能 / 改动先在 `spec/planned/` 建 spec 文档（`YYYY-MM-DD-<功能名>.md`）。
- 开发中移到 `spec/developing/`，完成后移到 `spec/implemented/`，放弃移到 `spec/discarded/`。
- 详见 `spec/README.md`。
