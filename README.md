# AI Daily Brief

每天北京时间 09:00 汇总前一个自然日的 AI 行业动态，完成采集、清洗、事件去重、分类、重要性排序、基于来源的摘要，并通过 Resend 发送 HTML 邮件。

> 当前版本：`0.1.0`。项目代码可运行，但“稳定运行天数、发送成功率、节省时间”等数据必须在真实部署后由日志统计，不能把目标值当成既成结果写进简历。

## 工作流

```text
RSS / arXiv / GitHub API
          ↓
北京时间自然日过滤与文本清洗
          ↓
URL规范化 → 标题相似度 → 正文词元相似度聚类
          ↓
7类主题识别与五维重要性评分
          ↓
DeepSeek结构化摘要（无密钥时自动使用抽取式摘要）
          ↓
官方来源 / 多源报道 / 单一信源标记
          ↓
Jinja2 HTML → Resend → 运行数据写入SQLite
```

事实核验是“来源约束”，不是让大模型凭记忆判断真假：官方发布优先作为代表来源；同事件的独立来源会被保留；只有单一媒体来源的内容会被标记且评分不超过 60。摘要提示词明确禁止补充材料之外的事实。

## 功能

- 15 个预配 RSS/arXiv 信源（当前 12 个默认启用）及 6 个 GitHub Release 监控仓库
- 严格按 `Asia/Shanghai` 的前一自然日筛选
- URL、标题、正文相似度三层事件去重
- 模型产品、商业、融资、开源、研究、监管、应用 7 类分类
- 信源、影响、新颖性、交叉来源、相关性五维评分
- DeepSeek `deepseek-chat` 批量生成中文摘要和影响说明
- 无 DeepSeek 密钥时可降级运行，便于测试与故障容错
- 响应式 HTML 邮件、Resend 投递、SQLite 指标留痕
- 单一数据源失败隔离、GitHub Actions 定时执行、pytest 测试

## 本地运行

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

先运行完全离线的样例链路：

```powershell
python -m ai_daily_brief --sample --date 2026-07-10 --output data/sample.html
```

运行真实采集但不发送邮件：

```powershell
python -m ai_daily_brief --output data/latest.html
```

确认 HTML 后真实发送：

```powershell
python -m ai_daily_brief --send --output data/latest.html
```

执行测试：

```powershell
pytest -q
```

## 配置

复制 `.env.example` 为 `.env`，不要提交 `.env`：

| 变量 | 必需 | 用途 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 摘要时必需 | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-chat` |
| `RESEND_API_KEY` | 发送时必需 | Resend API 密钥 |
| `EMAIL_FROM` | 发送时必需 | Resend 已验证的发件地址 |
| `EMAIL_TO` | 发送时必需 | 收件邮箱 |
| `GITHUB_TOKEN` | 建议 | 提高 GitHub API 限额 |
| `SUPABASE_URL` | 否 | 第二阶段长期指标数据库地址 |
| `SUPABASE_SERVICE_ROLE_KEY` | 否 | 服务端写入指标的Supabase密钥 |
| `DATABASE_PATH` | 否 | 默认 `data/ai_daily.db` |

信源在 `config/sources.yaml` 中维护。生产启用前应逐一确认第三方网站的 RSS 可用性与使用条款；单个源失效不会中止整次任务。

## GitHub Actions 部署

1. 把仓库推送到 GitHub。
2. 在仓库 `Settings → Secrets and variables → Actions` 新增：
   `DEEPSEEK_API_KEY`、`RESEND_API_KEY`、`EMAIL_FROM`、`EMAIL_TO`。
3. 在 Actions 页面手动运行一次 `AI Daily Brief`，检查产物与邮件。
4. 主调度使用 `45 0 * * *`，即北京时间 08:45，避开 GitHub Actions 整点高峰；补偿调度使用 `15 1 * * *`，即 09:15。

两个调度共享并发锁。每个定时运行在发送前都会读取当日成功记录：主任务延迟时补偿任务会等待，补偿任务先完成时迟到的主任务也会跳过，从而兼顾补发与防重复。Resend请求还使用基于邮件内容的稳定幂等键，避免“服务端已接收、客户端响应超时”造成重复邮件。手动触发不受调度守卫限制，便于指定日期补发。GitHub 的 schedule 仍不是严格实时服务；若业务要求绝对准点，应迁移到云函数或服务器 cron。

手动运行可勾选 `dry_run`，仅生成并上传日报产物而不发送邮件，适合部署验证。

## 长期运行指标

系统始终把运行和逐信源指标写入本地SQLite。执行以下命令可生成汇总：

```powershell
python -m ai_daily_brief.metrics_report --database data/ai_daily.db
```

如需跨GitHub Actions任务长期累计，在Supabase SQL Editor执行 `supabase/migrations/001_metrics.sql`，然后配置仓库Secrets `SUPABASE_URL`和`SUPABASE_SERVICE_ROLE_KEY`。远程指标写入失败只记录日志，不会阻断日报发送。

GitHub Actions 的数据库文件只作为当次 artifact 保存 30 天，不是永久数据库。要统计长期指标，建议后续接入 PostgreSQL、对象存储或在每次运行结束时导出指标。

## 质量边界

- “官方来源”表示链接来自配置为官方的站点或官方 GitHub 仓库，不代表系统对全部主张做了独立审计。
- “多源交叉核验”表示系统将相似报道聚为同一事件；仍应人工检查融资金额、模型指标和政策条款。
- GitHub 搜索结果代表目标日有更新且符合主题/Star条件的仓库，不等同于官方 Trending 榜单。
- RSS 页面结构与地址会变化，真实部署后应监控 `source_errors` 并定期维护。

## 简历量化

SQLite 的 `runs` 表记录采集量、时间窗口数量、聚类后数量、最终条数、信源错误、LLM使用状态、发送状态和运行耗时。连续运行后，只使用真实统计值替换简历中的占位符：

> 接入 `[N]` 个 RSS/API 信源，日均处理 `[A]` 条信息，经事件聚类输出 `[B]` 条核心动态；连续运行 `[D]` 天，邮件发送成功率 `[R]%`，每日人工审核由 `[X]` 分钟降至 `[Y]` 分钟。

## 项目结构

```text
src/ai_daily_brief/
├── collectors/       # RSS、GitHub
├── processors/       # 清洗、去重、分类、评分
├── delivery/         # HTML与Resend
├── deepseek.py       # 结构化摘要
├── pipeline.py       # 主处理链路
├── database.py       # SQLite留痕
└── cli.py            # 命令行入口
```
