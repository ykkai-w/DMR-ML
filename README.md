# DMR-ML

基于机器学习的双重动量指数轮动策略

在线演示：[dmrml.cn](https://dmrml.cn)

---

DMR-ML = DMR（双重动量轮动）+ ML（机器学习风险门禁）。前半段负责决定"买什么"，后半段负责判断"现在该不该买"。

在沪深 300 与中证 1000 之间做动量轮动，并在每一次轮动前用一个随机森林分类器做风险评估：预测概率超过触发阈值时强制空仓，低于解除阈值时恢复持仓。

之所以选择沪深 300 与中证 1000，是因为两者都有对应的宽基 ETF 与指数基金，任何投资者都可以低成本地跟随操作。

---

## 方法

**DMR — Dual Momentum Rotation**
计算沪深 300 与中证 1000 的短期相对动量和绝对动量，两者均未达到阈值时空仓。

**ML — Machine Learning Risk Gate**
随机森林分类器预测未来 5 个交易日的下跌概率。双阈值迟滞机制（默认触发 40% / 解除 33%）减少临界区间的频繁切换。

**Purged Walk-Forward 验证**
训练窗口与测试窗口之间留出 gap，避免因标签重叠导致的数据泄露。特征仅基于历史价量的滚动统计量，不引入任何未来信息。

---

## 回测表现（2019-01-02 至 2026-04-03）

| 指标     | DMR-ML (Adagio) | Presto | 纯 DMR | 沪深 300 |
| -------- | :-------------: | :----: | :----: | :------: |
| 累计收益 |     186.2%      | 193.3% | 134.8% |  49.5%   |
| 年化收益 |     15.6%       | 16.0%  | 12.5%  |   5.9%   |
| 最大回撤 |     -12.7%      | -15.8% | -19.0% |  -45.6%  |
| 夏普比率 |      0.94       |  0.94  |  0.67  |   0.29   |

"纯 DMR"是在 Adagio 相同参数下关闭 ML 风控的消融结果。ML 风控使最大回撤从 -19.0% 改善到 -12.7%（相对降低 33%），年化收益提升 3.1 个百分点。Adagio 与 Presto 夏普比率一致，但 Presto 用更高交易频率换取略高的总收益，代价是更深的回撤。

回测为样本内结果，实际业绩可能因市场结构变化而显著不同。

---

## 核心功能

本仓库与 [dmrml.cn](https://dmrml.cn) 使用完全相同的代码，本地运行后可以得到一致的界面与交互。

- **策略概览** — 净值走势、核心指标、策略与基准对比
- **今日信号** — 每日操作建议、ML 风险概率仪表盘、决策推理面板
- **深度分析** — 回撤分析、月度收益热力图、收益分布、滚动夏普
- **交易记录** — 逐笔成交、持仓时长、盈亏分布
- **交易信号** — 历年轮动时序图

三种模型预设：

| 预设 | 定位 | 动量窗口 | 均线窗口 | 风险触发 | 风险解除 |
| ---- | ---- | -------- | -------- | -------- | -------- |
| Adagio | 稳健低回撤 | 20 | 14 | 40% | 33% |
| Presto | 灵敏搏收益 | 10 | 14 | 40% | 33% |
| Rubato | 参数自定义 | — | — | — | — |

Adagio 与 Presto 共用同一套 ML 风控，差别仅在动量计算周期的长短。两组参数分别通过网格搜索在稳健与激进两个风格区间内寻优得到。Rubato 在前端提供滑杆，可自行调整上述四个参数。

---

## 架构

- 后端：FastAPI + uvicorn
- 前端：原生 HTML / CSS / JavaScript，无前端框架
- 数据源：Tushare Pro
- 持久化：JSON / Supabase（订阅模块可选后端）

```
├── config.py                  # 参数配置
├── data_service.py            # 行情数据接入与缓存
├── models.py                  # ML 风险模型
├── backtest_engine.py         # 回测引擎
├── reports.py                 # 策略报表与信号生成
├── visualization.py           # 图表
├── subscription_service.py    # 邮件订阅
├── send_daily_email.py        # 每日推送入口
├── run.py                     # 命令行入口
└── web/
    ├── api.py                 # FastAPI 后端
    ├── templates/             # 前端页面
    └── static/                # 样式、脚本、插画
```

---

## 本地运行

**环境：** Python 3.9 – 3.11

```bash
git clone https://github.com/ykkai-w/DMR-ML.git
cd DMR-ML
pip install -r requirements.txt
```

复制 `.env.example` 为 `.env` 并填写：

```
TUSHARE_TOKEN=你的 Tushare Token        # tushare.pro/register 注册获取
ADMIN_PASSWORD=自定义管理密码
EMAIL_PASSWORD=SMTP 授权码              # 仅启用邮件订阅时需要
```

启动：

```bash
python run.py web        # Web 界面，访问 http://localhost:8000
python run.py backtest   # 命令行回测
python run.py signal     # 生成今日信号
```

---

## 自定义推送：接入 OpenClaw

仓库自带的邮件订阅足以满足基本需求，但邮件的到达率和时效性都不理想。如果希望把每日信号推送到**微信、飞书、iMessage、Telegram** 等即时通讯平台，推荐接入 [OpenClaw](https://github.com/openclaw/openclaw) —— 一个开源的自托管 AI 助手，原生支持上述平台。

### 接入思路

`send_daily_email.py` 每天收盘后执行一次，计算当日信号并通过 SMTP 发送。把发送环节替换成 HTTP 调用 OpenClaw，即可转发到任意支持的通讯平台。

### 操作步骤

**1. 部署 OpenClaw**

按 [OpenClaw 官方文档](https://github.com/openclaw/openclaw) 部署，配置好目标平台（企业微信机器人、飞书自定义机器人、iMessage 中继等）。记录 OpenClaw 的 HTTP 接口地址和对应的 channel / user ID。

**2. 新建推送适配器**

在项目根目录创建 `push_openclaw.py`：

```python
import os
import requests
from reports import SignalGenerator
from data_service import get_data_service
from models import MLRiskModel
from config import get_config

OPENCLAW_URL = os.environ["OPENCLAW_URL"]
OPENCLAW_TARGET = os.environ["OPENCLAW_TARGET"]


def build_signal_text() -> str:
    data_service = get_data_service()
    df300, df1000 = data_service.get_aligned_data()

    ml_probs = MLRiskModel().fit_predict(df300, verbose=False)
    config = get_config()
    signal_gen = SignalGenerator(
        df300, df1000, ml_probs,
        config.strategy.default_momentum_window,
        config.strategy.default_ma_window,
    )
    return signal_gen.format_signal_text()


def push():
    text = build_signal_text()
    requests.post(
        OPENCLAW_URL,
        json={"target": OPENCLAW_TARGET, "message": text},
        timeout=10,
    )


if __name__ == "__main__":
    push()
```

**3. 配置环境变量**

```
OPENCLAW_URL=http://your-openclaw-host:port/send
OPENCLAW_TARGET=your_wechat_or_feishu_channel_id
```

**4. 每日定时执行**

Linux crontab（每交易日 16:30）：

```
30 16 * * 1-5 cd /path/to/DMR-ML && /usr/bin/python push_openclaw.py >> push.log 2>&1
```

Windows 任务计划程序同理。

`SignalGenerator` 返回的是结构化字段，替换推送通道不涉及策略逻辑改动。

---

## 风险提示

本项目仅为学习与研究用途，不构成任何投资建议。历史回测表现不代表未来收益，A 股市场结构可能发生变化，使用前请自行评估风险。

---

## 许可证

MIT License. 见 [LICENSE](./LICENSE)。

---

## 关于

作者：Kai（中国农业大学 金融学 & 数据科学 在读）
联系：ykai.w@outlook.com
在线演示：[dmrml.cn](https://dmrml.cn)
