[中文](./README.md) | [English](./README.en.md)

# NovelForge

NovelForge 是一个面向长篇小说创作的 LLM 写作工作台，核心围绕持久化项目存储、检索增强、结构化工作流，以及未来的多 Agent 协作能力构建。

它更适合长期创作场景，例如同人文、网文、长篇原创小说，而不是一次性聊天生成。项目重点关注设定持续维护、上下文记忆、分层规划和迭代修订。

## 项目定位

大多数 LLM 写作工具更偏向短对话和单次生成。
NovelForge 想解决的是另一类问题：

- 基于项目的长期写作
- 长期记忆与设定维护
- 从总纲到章节的完整工作流
- 检索增强上下文注入
- 结构化审阅与校验
- 为后续工作流运行时和多 Agent 协作预留架构

这个项目同时也是：

- 一个实际可用的小说写作工具
- 一个用于学习 LLM 应用、RAG、工作流与 Agent 系统的实验平台

## 当前状态

NovelForge 已经不再是早期原型。

当前成熟度大致可以概括为：

- V1 写作工作台：已实现
- V1.1 持久化、校验与体验强化：已实现
- V2 检索基础：大部分已实现
- V3 工作流 / 状态系统基础：部分实现，已支持失败运行恢复
- V4 多 Agent 架构：规划中
- V5 评估系统：已实现章节级基础版本

## 核心能力

- 基于项目的故事存储
- Streamlit Web 界面
- 全书大纲生成
- 章节细纲生成
- 正文章节写作
- 章节审阅
- 根据章节内容更新记忆
- 表单化故事记忆编辑
- 可配置章节目标字数
- 长期项目的记忆压缩
- 全局 / 项目双层规则系统
- 面向项目与外部资料的检索中心
- 词法 / 语义 / 混合检索
- 带权威度与冲突提示的证据展示
- 检索调试面板，可查看 query terms、候选块和 rerank 结果
- 检索冲突裁决与持久化记录
- 角色 / 时间线 / 伏笔 / 一致性分析
- 章节质量评估与结构化评分报告
- 面向总纲、分卷、剧情段、章节的结构化规划讨论
- 审批式规划工件
- 一键章节流水线、运行快照与失败运行恢复
- 分卷 / 剧情段分层规划体系
- Arc 章节分配计划
- 轻量写作指导参数
- 应用内模型地址与密钥配置

## 设计原则

NovelForge 遵循几条核心原则：

1. 持久化优先于智能化
2. 工作流优先于多 Agent
3. 技能化优先于自治化
4. 一切以项目为中心
5. 通过 OpenAI-compatible 接口保持模型独立性

## 架构概览

当前高层流程：

```text
用户
-> Streamlit UI (app.py)
-> Skill Layer (skills.py)
-> Prompt Layer (prompts.py)
-> LLM Interface (llm.py)
-> OpenAI-compatible API
-> Memory / Storage / Retrieval
```

主要文件职责：

- `app.py`：界面与交互流程
- `skills.py`：写作与分析能力
- `prompts.py`：提示词模板与拼装
- `llm.py`：模型抽象与 API 集成
- `memory.py`：持久化存储与项目数据管理
- `schemas.py`：结构化输出契约与校验
- `retrieval.py`：索引、检索与上下文格式化

## 典型工作流

NovelForge 支持直接生成，也支持“先讨论，再生成”的规划方式。

典型章节流程：

1. 讨论故事或章节方向
2. 生成总纲或章节细纲
3. 生成章节正文
4. 审阅章节质量与一致性
5. 更新故事记忆
6. 需要时查看分析报告或检索证据
7. 需要时执行章节评估，或从失败流水线运行继续恢复

系统也支持一键流水线：

```text
Plan -> Write -> Review -> Update Memory
```

## 检索与知识支持

NovelForge 内置项目级检索层，可同时处理内部写作资料和外部参考资料。

当前支持的检索能力包括：

- 项目知识检索
- 原作 / 参考资料检索
- 文档切块索引
- 语义向量检索
- 词法 + 语义混合排序
- 来源权威度加权
- 按作用域分组证据
- 当项目证据与外部证据冲突时给出提示
- 保存冲突裁决，后续检索会把裁决作为项目知识召回
- 可选检索调试信息，帮助排查召回和排序原因

## 项目存储结构

每个故事会作为独立项目存放在 `data/projects/` 下。

典型结构：

```text
data/
  global_rules.json
  projects/
    your_project/
      memory.json
      rules.json
      outline.md
      volumes/
      arcs/
      chapter_outlines/
      chapters/
      reviews/
      analysis/
      evaluation/
      retrieval/
      runs/
```

这样可以把规划、正文、审阅、分析和检索工件统一挂在同一个项目下，而不是散落在聊天记录中。

新增工件包括：

- `arcs/arc_xxx.chapter_plan.json`：剧情段章节分配计划
- `evaluation/chapter_xxx.md` / `.json`：章节评估报告和结构化评分
- `retrieval/conflict_resolutions.json`：检索冲突裁决记录
- `runs/*.json`：可恢复流水线运行快照

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置模型访问

你可以通过两种方式配置模型：

- 手动编辑 `.env`
- 在应用内使用 `模型配置` 页面创建并切换多套配置档案

典型环境变量：

```env
LLM_API_KEY=
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_EMBEDDING_MODEL=text-embedding-3-small
```

### 3. 启动应用

```bash
streamlit run app.py
```

## 本地 Windows 便携版构建

NovelForge 也可以打包成一个本地 Windows 便携版，双击后自动启动 Streamlit 服务并打开浏览器。

### 发布形态

目标分发形式为：

- `NovelForge.exe` 作为小型启动器
- 随包附带 `.venv` 运行时
- 保留项目源码文件
- 使用本地 `data/` 目录存放项目数据

用户启动 `NovelForge.exe` 后，程序会：

1. 在 `127.0.0.1` 启动本地 Streamlit 服务，优先尝试 `8501`
2. 等待应用可访问
3. 自动打开浏览器

### 构建步骤

1. 创建并准备本地虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

2. 在 PowerShell 中运行构建脚本：

```powershell
.\build_release.ps1 -Version v0.1.0
```

3. 脚本会自动：

- 在 `.venv` 中安装 `pyinstaller`
- 根据 `launcher.py` 构建 `NovelForge.exe`
- 组装 `release/NovelForge-Portable/`
- 生成 `release/NovelForge-windows-portable-v0.1.0.zip`
- 在 `release/` 下保存本地构建日志

### 使用说明

- 建议把便携版解压到可写目录，例如 `D:\Apps\NovelForge\`
- 不建议放在 `C:\Program Files\` 这类受保护目录
- 用户数据会保存在同目录下的 `data/` 和 `.env`
- 启动器会优先使用 `8501`，必要时会自动回退到附近端口
- 如果启动失败，可查看应用目录中的 `launcher.log`
- 如果候选端口之一被其他应用占用，启动器会自动尝试下一个端口，而不是误打开错误页面
- 构建日志会保存在 `release/build_release-<version>.log`

## 模型支持策略

项目围绕 OpenAI-compatible API 层设计。

当前默认模型方向：

- DeepSeek

规划中或兼容方向：

- GPT
- Claude
- Qwen
- 本地或自托管的 OpenAI-compatible 模型

## Roadmap

### V2 后端强化

- 引入专用向量数据库后端
- 更深入的事实级冲突推荐逻辑
- 更强的检索稳定性

### V3 工作流运行时落地

- 图式 / runtime 工作流编排
- 更完整的一等公民级别重试与恢复策略
- 支持分支式工作流执行

### V4 多 Agent 架构

计划中的角色包括：

- ChiefEditorAgent
- PlotAgent
- WriterAgent
- ReviewAgent
- MemoryAgent
- ResearchAgent

### V5 评估系统

当前已实现章节级评估基础版本，支持保存 Markdown 和 JSON 报告。

已支持的评估维度包括：

- 角色一致性
- 剧情推进质量
- 信息密度
- 情绪冲击
- 伏笔处理
- 文笔质量

后续计划：

- 跨版本章节比较
- 跨运行指标追踪
- 面向模型和 Prompt 变更的自动评估集

## 开发说明

项目在职责划分上保持明确边界：

- UI 逻辑尽量保持在 `app.py` 的轻量层面
- 新写作能力优先通过 `skills.py` 扩展
- Prompt 工程集中在 `prompts.py`
- 持久化逻辑集中在 `memory.py`
- 模型适配尽量只改 `llm.py`
- 结构化 LLM 输出优先通过 `schemas.py` 定义

更详细的实现说明和路线规划请查看 `project.md`。

## License

当前仓库中尚未包含许可证文件。
