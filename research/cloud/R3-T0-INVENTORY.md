# R3-T0 仓库盘点与安全扫描

- 作者：三号研究员（云端 Fable 会话）
- 时间：2026-09-24 12:26 UTC（容器时钟；北京时间 20:26）
- 仓库：`ykkai-w/DMR-ML`（简报中写作 "DMRML"，实际远程名为 `DMR-ML`）
- 结论先行：**未发现任何真实凭据**（见第 4 节）。`research/` 目录整体不存在，T5/T7/T8 的实跑部分与 T3/T4 的实跑部分不可做（见第 6 节）。

## 1. Git 基本情况

```
origin  https://github.com/ykkai-w/DMR-ML (fetch/push)
会话启动分支：claude/affectionate-fermi-4w92hb（与 origin/main 同一提交）
```

全部提交历史只有 2 条：

| 提交 | 日期 | 说明 | 变更 |
|---|---|---|---|
| `b637cd1` | 2026-07-15 | Update README.md | README +18/−1 |
| `4f3a996` | 2026-04-05 | DMR-ML | 初始导入，29 文件，+11236 行 |

分支：`main`、`claude/affectionate-fermi-4w92hb`（本会话指定分支）。没有其他分支或标签。

## 2. 文件树（到二级目录，带文件数）

被跟踪文件共 29 个，11251 行。

```
根目录 (17 文件)
  .env.example  .gitignore  LICENSE  README.md  __init__.py
  backtest_engine.py  config.py  data_service.py  models.py  reports.py
  requirements.txt  run.py  runtime.txt  send_daily_email.py
  subscription_service.py  utils.py  visualization.py
web/ (12 文件)
  web/api.py
  web/static/ (9 文件)：css/style.css, js/app.js, favicon.svg, mascot-pixel.svg,
                        demo-anim-{a,b,c,d}.html, logo-preview.html
  web/templates/ (2 文件)：index.html, admin.html
```

按行数最大的几个文件：`web/static/css/style.css` 1709、`web/static/js/app.js` 1296、`visualization.py` 769、`web/templates/index.html` 707、`subscription_service.py` 630、`web/api.py` 605、`models.py` 538、`backtest_engine.py` 508。

工作区没有未跟踪或被忽略的文件（容器是干净克隆）。

## 3. 简报要求核对的文件/目录

| 路径 | 是否存在 | 备注 |
|---|---|---|
| `research/` | 否 | 整个目录不存在 |
| `research/claude/` | 否 | 因此 `*.md` 卡片数 = 0，`*.py` = 0 |
| `research/codex/` | 否 | |
| `PROGRESS.md` | 否 | |
| `research/experiments.jsonl` | 否 | |
| `research/validation.py` | 否 | |
| `config.py` | 是 | 210 行；只含 `os.environ.get("TUSHARE_TOKEN", "")` 读取，无字面量凭据 |
| `.env` | 否 | `.gitignore` 第 138 行已忽略 `.env` |
| `.env.example` | 是 | 10 行，三个变量名均为空值占位 |
| 被跟踪的 `*.parquet/*.pkl/*.csv/*.json/*.jsonl/*.h5/*.npy` | 无 | `git ls-files` 按扩展名匹配为空；`.gitignore` 第 149–150 行忽略 `cache_dmr_pro/`、`subscribers.json` |

简报中提到的 `sleeve_mapping_clarification_20260918.py`、`company_v2_features_full_20260917.py`、`company_v2_monthly_paged_pull_20260917.py`、`CANDIDATE-REPLICATION-SPEC-v2-20260922.md` 在本仓库任何分支/提交中都不存在。推测这些文件只在研究负责的本机，从未推送到 GitHub。

## 4. 密钥扫描（最高优先级项）

**结果：未发现真实凭据。** 以下是跑过的扫描与逐条判定。

| 扫描 | 命中 | 判定 |
|---|---|---|
| 简报指定的正则 `(token\|api_key\|secret\|password) *[:=] *["'][A-Za-z0-9_\-]{16,}` | 0 | 无 |
| 宽泛的 key 类赋值 `(token\|api_?key\|secret\|passw(or)?d\|auth\|credential\|bearer\|private_key)\s*[:=]` | 14 处 | 全部为环境变量读取或空占位，见下表 |
| 长字母数字串（≥24）在 `*.py/*.txt/*.md/*.example` | 0 | 无 |
| 长字母数字串（≥32）在 `web/static/js`、`web/templates`、`web/static/*.html` | 0 | 无 |
| 常见前缀 `sk-` / `ghp_` / `AKIA` / `xox[bap]-` / `AIza` | 0 | 无 |
| URL 内嵌凭据 `://user:pass@` | 0 | 无 |
| 密钥类文件名（`.env`、`secret`、`credential`、`.pem`、`.key`、`id_rsa`、`token`） | 仅 `.env.example` | 占位文件 |
| 全历史（`git log -p --all`）被删除行中的凭据模式 | 0 | 无 |
| 全历史新增/删除的密钥类文件 | 0 | 无 |

宽泛模式的 14 处命中逐条判定（只列路径与行号）：

- `.env.example:3`、`:6`、`:10` — `TUSHARE_TOKEN=`、`ADMIN_PASSWORD=`、`EMAIL_PASSWORD=`，值为空。
- `README.md:122`–`124` — 文档示例，中文占位文字。
- `config.py:25` — `os.environ.get("TUSHARE_TOKEN", "")`。
- `web/api.py:551` — `ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")`。
- `web/api.py:562`、`:564`、`:570`、`:572`、`:597`、`:601` — 管理接口的 `password: str = Query(...)` 参数与比较语句，无字面量。

### 4.1 非凭据但值得所有者知道的两点（我不改动，只报告）

1. **`subscription_service.py:56`** — 硬编码了一个发件人邮箱地址（个人 QQ 邮箱）。不是凭据，但属于个人信息且已随公开仓库发布；建议改为环境变量。`README.md:230` 与 `web/templates/index.html:222` 的联系邮箱看起来是有意公开的。
2. **`web/api.py:551`、`:564`、`:572`、`:601`** — `ADMIN_PASSWORD` 缺省值为空字符串，且用 `==` 比较；若部署时未设置该环境变量，`?password=`（空串）即可通过管理接口鉴权。密码还以 GET 查询参数传递，会进入访问日志。这是生产文件，按简报第 4 条我不改，建议所有者自行处理（至少：未设置时拒绝所有管理请求；改为 POST；用 `hmac.compare_digest`）。

## 5. 运行环境

- 容器：Linux，Python 3.11.15；仓库依赖未预装，我额外安装了 `pandas 3.0.6`、`numpy 2.4.6`、`pytest 9.1.1`、`pyarrow 25.0.1`（只用于 T1–T5 的合成数据测试；注意 pandas 3.x 与本机可能不同，测试写法会避免 2.x/3.x 行为差异）。
- 网络：经代理可达 `scholar.google.com`、`semanticscholar.org`、`pypi.org`；`ssrn.com` 返回 403；`api.crossref.org` 返回 429（限流，可重试）。WebSearch 工具可用。T6 可做。
- 没有任何研究数据（与简报一致）。

## 6. 各任务可行性（以本盘点为准）

| 任务 | 可行性 | 说明 |
|---|---|---|
| T1 采集器加固 | 可做 | 代码 + 合成 `fn` 的 pytest |
| T2 面板质量门 | 可做 | 代码 + 合成面板 pytest |
| T3 登记册/进度 lint | 代码可做；实跑不可做 | `experiments.jsonl`、`PROGRESS.md` 不存在 |
| T4 DEV 边界审计器 | 代码可做；对 `research/claude/*.py` 实跑不可做 | 改为对仓库根目录 `*.py` 实跑作演示，报告中明确标注对象 |
| T5 规格检查器 | 代码可做；实跑不可做 | 规格文件不存在 |
| T6 文献综述 | 可做 | 联网可核实引用；SSRN 不可达，引用优先走期刊/Scholar/Semantic Scholar |
| T7 代码审阅 | 不可做 | 三个目标文件不在仓库 |
| T8 `validation.py` 测试 | 不可做 | 文件不在仓库 |

如果研究负责把 `research/` 目录推到任一分支，T3/T4/T5 实跑与 T7/T8 可立即补做。

## 7. 分支与 PR 约定的说明

会话系统提示指定开发分支为 `claude/affectionate-fermi-4w92hb`；简报要求每任务一个 `cloud/r3/<task-id>` 分支加一个 PR。两者不冲突：我按简报用 `cloud/r3/<task-id>` 分支（各自从 `origin/main` 切出）开 PR，最后把累计状态再推一份到会话指定分支作为备份。`R3-LOG.md` 是追加式共享文件，各任务分支里带的是截至该任务的累计日志；按任务顺序合并不会冲突，乱序合并只会在日志末尾产生平凡冲突。

## 8. 执行顺序

所有者补充要求"探索新收益方向优先"。我没有数据，能为这个目标直接贡献的是 T6（文献综述）以及附在其后的"可直接落地的候选方向清单"。因此顺序为：T0 → T6 → T1 → T2 → T4 → T3 → T5；T7、T8 跳过并在总汇报中说明。
