# spec/ — 需求与改动状态管理

本目录用「状态文件夹」管理项目的每个功能 / 改动（spec）。每个 spec 是一份 Markdown 文档，随开发进度在四个状态文件夹之间移动。

## 状态（正确英文）

| 文件夹 | 英文 | 含义 |
|---|---|---|
| `planned/` | planned | 已规划：spec 已写好，尚未开工 |
| `developing/` | developing | 开发中：正在实现 |
| `implemented/` | implemented | 已实现：已完成并通过验证 |
| `discarded/` | discarded | 已废弃：放弃或否决，保留记录备查 |

> 命名说明：最初写成 `planed / developing / implement / discard`。其中 `planed` 是「用刨子刨平」的意思（应作 planned）；`implement`、`discard` 是动词，作状态名应统一用过去分词 / 形容词。最终定为 **planned / developing / implemented / discarded**。

## 工作流

1. 有新需求或改动，先在 `planned/` 建 spec：`YYYY-MM-DD-<功能名>.md`。
2. 开始开发，把 spec 移到 `developing/`。
3. 完成并验证通过，移到 `implemented/`。
4. 中途放弃或否决，移到 `discarded/`（不删除，保留决策记录）。

## 每个 spec 文档建议包含

- 目标 / 背景
- 改动范围（涉及哪些文件、明确哪些不碰）
- 验收标准
- 状态变更记录（日期 + 从哪移到哪）
