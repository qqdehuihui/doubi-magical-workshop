# AI 学习助手

面向大学生的 AI 学习助手单页 Web 应用：上传课程资料（**PDF / PPTX / DOCX**），自动完成
**多格式解析（保留来源定位）→ 五层重难点分析 → 智能模拟考试（六题型 + 质量审核）→ 历年考试资料库统计 → 基于课件的问答**。

> 当前默认使用 **Mock Provider**：基于课件原文片段生成结构化测试数据，用于验证完整业务闭环。
> Mock 成功不代表真实 AI 推理能力；界面与 API 响应均明确标注数据来源（`provider.mock`）。切换到真实模型见下文 Provider 配置。

## 架构

```
frontend/  React + TypeScript + Vite（上传/重难点/模拟考试/问答/历年资料库 五个页签）
backend/
├── app/api/                # 路由层（documents / analysis / exams / llm）
├── app/core/
│   ├── documents/          # ★ 统一解析层：parsers.py 按格式分发，产出 DocumentBlock
│   │   ├── blocks.py       #   DocumentBlock 定义 + 来源定位标签 + 文档摘要（unit_count/unit_label）
│   │   └── parsers.py      #   PDF(pypdf)/PPTX(python-pptx)/DOCX(python-docx)；格式嗅探与校验互相独立
│   ├── providers/          # ★ 统一模型抽象层：业务模块禁止直连任何模型 SDK
│   │   ├── base.py         #   GenerationRequest/Result + BaseProvider
│   │   ├── mock.py         #   MockProvider：证据驱动、明确标记测试数据、无证据时返回“证据不足”
│   │   ├── openai_compatible.py  # OpenAICompatibleProvider：统一超时/限流/鉴权/网络异常映射
│   │   └── __init__.py     #   get_provider() 工厂 + run()（记录 provider/model/耗时/token/状态，绝不记录 Key）
│   ├── qoder_client.py     #   Qoder CN Cloud Agents 只读连通性检查（第一阶段，见下）
│   ├── retrieval.py        # 分块检索（按页/幻灯片/章节）+ 关键词匹配 + 上下文预算
│   ├── config.py / errors.py / storage.py
└── app/modules/
    ├── keypoints/          # 五层重难点分析（框架/核心知识点/重难点/可能考查/历年高频）
    ├── questions/          # 模拟考试：六题型 × 难度 × Bloom 认知层次 × 章节范围
    ├── review/             # ★ 题目质量审核：确定性规则（options/答案/解析/固定填充词/重复题）+ 模型语义审查合并
    ├── qa/                 # 检索增强问答（引用来源定位）
    └── examdb/             # ★ 历年考试资料库：拆题、考点归一化、真实统计
```

数据流：文件 → 魔数/扩展名双重校验 → 对应解析器 → 统一 `DocumentBlock` 存 `data/{doc_id}.json`
→ 检索层按问题取相关片段（受字符预算限制，绝不整本传入）→ Provider → 结果携带来源定位与 `provider` 元信息。

## 多格式解析与来源定位

| 格式 | 解析库 | 定位标签 | 章节单位 |
|---|---|---|---|
| `.pdf` | pypdf | `第 N 页` | 页 |
| `.pptx` | python-pptx | `第 N 张幻灯片` | 幻灯片 |
| `.docx` | python-docx | `章节 一/二 / 第 N 段`、`表格 N` | 标题层级/段落/表格 |

- 文件类型以**内容魔数**（`%PDF`、zip 内部结构）为准，扩展名与内容不符报 `INVALID_FILE`，不混用来源编号；
- 旧格式 `.ppt` / `.doc` 明确提示「请用 Office 另存为 .pptx / .docx 后上传」，不做猜测性解析；
- 扫描版 PDF / 无文字内容的文档返回 `SCANNED_PDF` / `EMPTY_DOCUMENT` 并提示需人工处理——**图片 OCR 当前未支持，不谎报成功**。

## 五层重难点分析（kepoints_v2）

① 课程核心框架（章节 + 关联关系）→ ② 核心知识点 → ③ 重难点解析（为什么难 + 易混对比）→
④ 可能考查内容（推测）→ ⑤ 历年高频考点（**仅来自真实导入的考试资料统计，模型不得编造**）。

四个指标严格区分，响应内含 `metrics_legend`：

| 指标 | 含义 | 来源 |
|---|---|---|
| 课件强调度 `emphasis` | 内容在课件中的重复/突出程度 | 课件文本 |
| 知识点重要性 `importance` | 定义/原理/公式等知识属性 | 课件文本 |
| 推测考查价值 `priority` | 基于强调度的复习优先级（非统计结论） | 推测 |
| 历史考试频率 `historical_frequency` | 真实考频 | 仅历年资料库统计 |

未导入考试资料时，第五层固定显示：
「当前仅基于教师课件分析，尚未导入历年考试资料，无法统计真实考频。上传往年试卷后可生成历年高频考点分析。」

## 历年考试资料库（examdb）

- 登记：课程 ID、资料类型（试卷/题库/复习提纲）、年份、文件名、题目、题型、考点、分值；
- **年份/题型/分值无法识别时记为「未知」，不做猜测**（如英文版式分值标注、无年份文件名）；
- 考点归一化：去分值标注/停用词/连接词切分 + 相似合并，同一知识点不同表述（“牛顿第二定律”/“牛顿第二定律的内容”）合并统计，跨资料同义合并；
- 统计：考点次数、年份跨度、题型分布、合计分值、章节覆盖、真题示例；全部来自真实导入数据。

## 智能模拟考试

六题型（单选/多选/判断/填空/简答/综合题）× 难度（基础/中等/较难/挑战）× Bloom 认知层次（记忆…创造，与难度独立）× 章节范围筛选。

- 干扰项必须基于易混淆概念/条件颠倒等，**禁止「正确答案」「以上都是」等无依据固定填充**；
- 每题附解析；选择题附每个错误选项为何错；简答/综合题附参考答案与评分要点；
- 质量审核 = 确定性规则 +（可用时）模型语义审查；不合格题目重新生成一次，仍不合格则**排除出卷面**并在页面上可查排除原因。

## 环境要求

- Node.js ≥ 18（本机安装于 `C:\Program Files\nodejs`，若终端找不到 `node` 请加入 PATH 或重启终端）
- Python ≥ 3.12（开发验证使用 3.14）

## 快速开始

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env      # Mock 模式无需填 Key，可直接启动
.venv/Scripts/python -m uvicorn app.main:app --port 8000 --reload
```

接口文档：http://127.0.0.1:8000/docs ；健康检查 `GET /api/healthz` 返回当前 Provider 状态。

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # 默认 http://localhost:5173（端口被占用时自动递增），/api 已代理到 8000
```

### 3. 测试

```bash
cd backend
.venv/Scripts/python -m pytest tests -q   # 当前 123 项全部通过
```

### 4. 样例文件

```bash
backend/.venv/Scripts/python backend/scripts/make_samples.py         # PDF 样例（含扫描版/损坏/空文件）
backend/.venv/Scripts/python backend/scripts/make_office_samples.py  # PPTX/DOCX 课件 + 历年真题 DOCX/PDF
```

## Provider 配置（backend/.env，仅存后端）

| 变量 | 说明 | 默认 |
|---|---|---|
| `LLM_PROVIDER` | `mock`（测试闭环）或 `openai`（真实模型） | `mock` |
| `OPENAI_API_KEY` | 真实模型密钥，**必填于 openai 模式，不得入库** | 空 |
| `OPENAI_BASE_URL` | OpenAI 兼容地址（如 DeepSeek：`https://api.deepseek.com/v1`） | OpenAI 官方 |
| `LLM_MODEL` | 模型名 | `gpt-4o-mini` |
| `LLM_TIMEOUT` | 单次调用超时（秒） | 90 |
| `MAX_FILE_MB` | 上传大小上限 | 50 |
| `MAX_GEN_CHARS` | 单次处理文本上限，超出提示分章上传 | 60000 |
| `DATA_DIR` | 解析缓存目录 | 仓库根 `data/`（已 gitignore） |

### Qoder CN Cloud Agents（接入中，第一阶段）

Cloud Agents 是 **Agent/Session/Event API**，不是 OpenAI Chat Completions；密钥是 PAT（个人访问令牌），只允许填在 `backend/.env`（已 gitignore，勿提交、勿发聊天窗口、勿写日志）。

| 变量 | 说明 | 默认 |
|---|---|---|
| `QODER_ACCESS_TOKEN` | Qoder CN 个人访问令牌（PAT） | 空 |
| `QODER_API_BASE_URL` | Cloud Agents API 地址 | `https://api.qoder.com.cn` |
| `QODER_OPENAPI_BASE_URL` | OpenAPI 管理地址（预留） | `https://openapi.qoder.com.cn` |
| `QODER_MODEL` | Cloud Agents 模型标识 | `ultimate` |
| `QODER_TIMEOUT` | 只读检查超时（秒） | 20 |

**第一阶段（已完成）为只读连通性检查**：`GET /api/llm/health` 检查配置完整性、以 Bearer PAT 调用
`GET /api/v1/cloud/environments` 与 `GET /api/v1/cloud/models`，返回认证结果、可用环境/模型列表与错误分类
（`not_configured` / `auth_failed` / `permission_denied` / `insufficient_credits` / `rate_limited` / `timeout` / `network_error` / `api_error`）。
本阶段不创建资源、不发送推理请求。当前账户未配置 PAT，状态为 `not_configured`（未验证，不代表失败）。
第二/三阶段（认证通过后进行）：最小化标记测试调用 → `QoderCloudAgentProvider` 接入统一 Provider。MockProvider 始终保留为默认。

## API 一览

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/documents` | 上传课件（PDF/PPTX/DOCX，魔数校验、统一解析；`course_id` 可选） |
| GET | `/api/documents/{doc_id}` | 文档元信息（file_type/unit_count/unit_label/sections） |
| POST | `/api/documents/{doc_id}/key-points` | 五层重难点分析 + 历史考频联动 + metrics_legend |
| POST | `/api/documents/{doc_id}/questions` | 模拟考试 `{count, types, difficulty, cognitive, chapters}`，响应含 `review`/`excluded` |
| POST | `/api/documents/{doc_id}/chat` | 检索增强问答（无证据时明确“证据不足”，不调模型；引用来源定位） |
| POST | `/api/exams` | 上传历年资料（表单：`file` + `course_id`/`material_type`/`year` 可选；前端资料库页要求先填课程） |
| GET | `/api/exams?course_id=` | 已导入资料列表 |
| GET | `/api/exams/frequent-points?course_id=&doc_id=` | 历年考点统计（带 `doc_id` 时联动课件章节；无资料时 `available=false` + 固定提示） |
| DELETE | `/api/exams/{exam_doc_id}` | 删除某份资料及其统计 |
| GET | `/api/healthz` | 健康检查 + Provider 配置状态 |
| GET | `/api/llm/health` | Qoder Cloud Agents 只读连通性检查（配置/PAT 认证/环境/模型） |

所有生成类响应携带 `provider: {name, model, elapsed_ms, mock, disclaimer?}`，前端明确区分测试数据与真实 AI 结果。

## 错误码

`UNSUPPORTED_FORMAT`（415，含 .ppt/.doc 另存提示）/ `INVALID_FILE`（415，扩展名与内容不符或损坏）/
`EMPTY_FILE`（400）/ `FILE_TOO_LARGE`（413）/ `INVALID_PDF` / `EMPTY_PDF` / `SCANNED_PDF`（415，需 OCR）/
`EMPTY_DOCUMENT`（415，无可提取文字）/ `DOC_TOO_LONG` / `DOC_NOT_FOUND`（404）/ `EXAM_NOT_FOUND`（404）/
`NO_EVIDENCE`（422）/ `INVALID_COUNT` / `INVALID_TYPES` /
`LLM_NOT_CONFIGURED`（503）/ `LLM_PROVIDER_UNSUPPORTED` / `LLM_AUTH`（401）/ `LLM_RATE_LIMIT`（429）/
`LLM_TIMEOUT`（504）/ `LLM_NETWORK`（502）/ `LLM_ERROR`（502）/ `NETWORK_ERROR`（前端）

统一返回 `{"code": "...", "message": "..."}`。

## 已知限制

- **PDF 解析沿用 pypdf**（升级任务书曾建议 PyMuPDF；现有能力已满足页码定位需求，未引入新依赖，属有意偏差）
- 扫描版 PDF / 图片内容不做 OCR，给出明确提示
- 检索为关键词匹配（MVP），后续可替换 embedding 检索
- 考点归一化以字面相似合并为主，纯英文题干考点（如 `energy`）标签仍偏粗；章节覆盖为字面近似匹配
- 超长文档不自动分块，提示按章节拆分上传
- Mock 结果基于原文摘录拼接，无推理质量，仅用于流程验证；真实 LLM 路径未配置 Key，尚未做真实推理验收
