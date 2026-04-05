"""
DMR-ML - FastAPI 后端
========================
将现有策略代码包装成 REST API
"""

import sys
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from config import get_config
from data_service import DataService
from models import DMRStrategy, MLRiskModel, DMRMLStrategy
from backtest_engine import BacktestEngine
from reports import MetricsCalculator, TradeAnalyzer, SignalGenerator
from visualization import DashboardCharts
from subscription_service import SubscriptionManager, load_subscribers, delete_subscriber, subscribe_email, EmailSender

BEIJING_TZ = timezone(timedelta(hours=8))

# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(title="DMR-ML API", version="1.0")

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================
# 全局缓存（替代 Streamlit 的 st.cache_data）
# ============================================================

class AppState:
    """全局应用状态，缓存数据和计算结果"""
    def __init__(self):
        self.df300: Optional[pd.DataFrame] = None
        self.df1000: Optional[pd.DataFrame] = None
        self.ml_probs: Optional[pd.Series] = None
        self.result_ml = None
        self.result_base = None
        self.bench: Optional[pd.Series] = None
        self.is_loaded = False
        self.last_params = {}
        self.active_model = "adagio"
        self._cache = {}  # 多模型缓存: params_key -> (ml_probs, result_ml, result_base, bench)

    def load_data(self):
        """加载市场数据（使用对齐后的数据，与 Streamlit 版本一致）"""
        print(">>> 正在加载市场数据...")
        ds = DataService()
        self.df300, self.df1000 = ds.get_aligned_data()
        print(f">>> 数据加载完成: CSI300={len(self.df300)}条, CSI1000={len(self.df1000)}条")

    def train_and_backtest(self, momentum_window=20, ma_window=14,
                           risk_trigger=0.40, risk_release=0.33):
        """训练 ML 模型并运行回测"""
        params_key = (momentum_window, ma_window, risk_trigger, risk_release)
        if self.is_loaded and self.last_params == params_key:
            return  # 参数没变，跳过

        # 检查缓存
        if params_key in self._cache:
            cached = self._cache[params_key]
            self.ml_probs = cached['ml_probs']
            self.result_ml = cached['result_ml']
            self.result_base = cached['result_base']
            self.bench = cached['bench']
            self.is_loaded = True
            self.last_params = params_key
            print(f">>> 命中缓存: mom={momentum_window}, ma={ma_window}")
            return

        # 设置风险阈值
        config = get_config()
        config.ml.risk_trigger_threshold = risk_trigger
        config.ml.risk_release_threshold = risk_release

        print(f">>> 参数: mom={momentum_window}, ma={ma_window}, "
              f"trigger={risk_trigger:.0%}, release={risk_release:.0%}")

        print(">>> 正在训练 ML 风险模型...")
        ml = MLRiskModel()
        self.ml_probs = ml.fit_predict(self.df300, verbose=True)

        print(">>> 正在执行回测...")
        engine = BacktestEngine()
        # DMR-ML 策略
        self.result_ml = engine.run_backtest(
            self.df300, self.df1000,
            momentum_window, ma_window,
            ml_probs=self.ml_probs,
            strategy_name="DMR-ML"
        )
        # DMR 基础策略
        self.result_base = engine.run_backtest(
            self.df300, self.df1000,
            momentum_window, ma_window,
            ml_probs=None,
            strategy_name="DMR"
        )
        # 基准
        common_idx = self.df300.index.intersection(self.df1000.index)
        bench = self.df300['close'].loc[common_idx]
        self.bench = bench / bench.iloc[0]

        # 存入缓存
        self._cache[params_key] = {
            'ml_probs': self.ml_probs,
            'result_ml': self.result_ml,
            'result_base': self.result_base,
            'bench': self.bench,
        }

        self.is_loaded = True
        self.last_params = params_key
        print(">>> 所有计算完成")

    def ensure_ready(self, momentum_window=20, ma_window=14,
                     risk_trigger=0.40, risk_release=0.33):
        """确保数据已加载且模型已训练"""
        if self.df300 is None:
            self.load_data()
        self.train_and_backtest(momentum_window, ma_window,
                                risk_trigger, risk_release)


state = AppState()


# ============================================================
# 模型预设参数
# ============================================================

MODEL_PRESETS = {
    "adagio": {
        "name": "Adagio",
        "subtitle": "稳健 · 低回撤",
        "momentum_window": 20,
        "ma_window": 14,
        "risk_trigger": 0.40,
        "risk_release": 0.33,
    },
    "presto": {
        "name": "Presto",
        "subtitle": "激进 · 高收益",
        "momentum_window": 10,
        "ma_window": 14,
        "risk_trigger": 0.40,
        "risk_release": 0.33,
    },
}


@app.get("/api/models")
async def get_models():
    """获取可用模型列表"""
    return json_response(MODEL_PRESETS)


@app.on_event("startup")
async def warmup():
    """服务启动时预热 Adagio 和 Presto 模型"""
    import asyncio
    def _warmup():
        print("=" * 50)
        print(">>> 启动预热：预计算 Adagio + Presto ...")
        state.load_data()
        for model_id, preset in MODEL_PRESETS.items():
            print(f">>> 预热模型: {preset['name']}")
            state.train_and_backtest(
                preset['momentum_window'], preset['ma_window'],
                preset['risk_trigger'], preset['risk_release'],
            )
        print(">>> 预热完成，两个模型已缓存")
        print("=" * 50)
    await asyncio.to_thread(_warmup)


# ============================================================
# JSON 序列化辅助
# ============================================================

class NumpyEncoder(json.JSONEncoder):
    """处理 numpy/pandas 类型的 JSON 编码器"""
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, (datetime,)):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        try:
            if pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
        return super().default(obj)


def json_response(data: dict) -> JSONResponse:
    """安全的 JSON 响应"""
    content = json.loads(json.dumps(data, cls=NumpyEncoder, ensure_ascii=False))
    return JSONResponse(content=content)


# ============================================================
# API 路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """首页"""
    html_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_status():
    """获取交易状态"""
    now = datetime.now(BEIJING_TZ)
    weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    is_weekend = now.weekday() >= 5
    hour = now.hour

    if is_weekend:
        status = "休市"
    elif 9 <= hour < 11 or (hour == 11 and now.minute <= 30):
        status = "交易中"
    elif (hour == 11 and now.minute > 30) or hour == 12:
        status = "午间休市"
    elif 13 <= hour < 15:
        status = "交易中"
    else:
        status = "已收盘"

    return json_response({
        "datetime": now.strftime('%Y-%m-%d %H:%M:%S'),
        "weekday": weekday_map[now.weekday()],
        "status": status,
        "is_trading": status == "交易中",
        "is_loaded": state.is_loaded,
    })


def _resolve_params(model: str = None, momentum_window: int = 20, ma_window: int = 14,
                     risk_trigger: float = 0.40, risk_release: float = 0.33):
    """从模型预设或自定义参数解析最终参数"""
    if model and model in MODEL_PRESETS:
        p = MODEL_PRESETS[model]
        return p["momentum_window"], p["ma_window"], p["risk_trigger"], p["risk_release"]
    return momentum_window, ma_window, risk_trigger, risk_release


@app.get("/api/init")
async def init_data(
    model: str = Query(None),
    momentum_window: int = Query(20, ge=10, le=40),
    ma_window: int = Query(14, ge=5, le=30),
    risk_trigger: float = Query(0.40),
    risk_release: float = Query(0.33),
):
    """初始化：加载数据 + 训练模型 + 回测"""
    try:
        mom, ma, trig, rel = _resolve_params(model, momentum_window, ma_window,
                                              risk_trigger, risk_release)
        if model:
            state.active_model = model
        state.ensure_ready(mom, ma, trig, rel)
        return json_response({"status": "ok", "message": "数据加载和模型训练完成"})
    except Exception as e:
        return json_response({"status": "error", "message": str(e)})


@app.get("/api/refresh")
async def refresh_data():
    """强制刷新数据"""
    state.df300 = None
    state.df1000 = None
    state.is_loaded = False
    state.last_params = {}
    try:
        state.ensure_ready()
        return json_response({"status": "ok", "message": "数据已刷新"})
    except Exception as e:
        return json_response({"status": "error", "message": str(e)})


@app.get("/api/overview")
async def get_overview(
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """策略概览：核心指标"""
    state.ensure_ready(momentum_window, ma_window)
    r = state.result_ml
    bench = state.bench

    # 基准指标（与 Streamlit render_overview_tab 完全一致的计算方式）
    bench_return = bench.iloc[-1] / bench.iloc[0] - 1
    n_years = len(bench) / 252
    bench_annual = (1 + bench_return) ** (1 / n_years) - 1
    bench_cummax = bench.cummax()
    bench_dd = ((bench - bench_cummax) / bench_cummax).min()
    bench_daily_ret = bench.pct_change().dropna()
    import numpy as np
    bench_sharpe = (bench_daily_ret.mean() * 252 - 0.03) / (bench_daily_ret.std() * np.sqrt(252)) if bench_daily_ret.std() > 0 else 0

    return json_response({
        "ml": {
            "total_return": r.total_return,
            "annual_return": r.annual_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "sortino_ratio": r.sortino_ratio,
            "win_rate": r.win_rate,
            "profit_loss_ratio": r.profit_loss_ratio,
            "total_trades": r.total_trades,
        },
        "base": {
            "total_return": state.result_base.total_return,
            "annual_return": state.result_base.annual_return,
            "max_drawdown": state.result_base.max_drawdown,
            "sharpe_ratio": state.result_base.sharpe_ratio,
        },
        "benchmark": {
            "total_return": bench_return,
            "annual_return": bench_annual,
            "max_drawdown": bench_dd,
            "sharpe_ratio": bench_sharpe,
        },
    })


@app.get("/api/chart/equity")
async def get_equity_chart(
    momentum_window: int = Query(20), ma_window: int = Query(14),
    include_dmr: bool = Query(True), include_bench: bool = Query(True),
    log_scale: bool = Query(True),
):
    """净值走势图"""
    state.ensure_ready(momentum_window, ma_window)
    charts = DashboardCharts()

    curves = {"DMR-ML": state.result_ml.equity_curve}
    if include_dmr:
        curves["DMR"] = state.result_base.equity_curve
    if include_bench:
        curves["沪深300"] = state.bench

    fig = charts.create_equity_curve(curves, log_scale=log_scale)
    return JSONResponse(content=json.loads(fig.to_json()))


@app.get("/api/signal")
async def get_signal(
    momentum_window: int = Query(20), ma_window: int = Query(14),
    risk_trigger: float = Query(0.40), risk_release: float = Query(0.33),
):
    """今日信号"""
    state.ensure_ready(momentum_window, ma_window)
    gen = SignalGenerator(
        state.df300, state.df1000, state.ml_probs,
        momentum_window, ma_window
    )
    signal = gen.generate_signal()
    return json_response(signal)


@app.get("/api/chart/drawdown")
async def get_drawdown_chart(
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """回撤分析图"""
    state.ensure_ready(momentum_window, ma_window)
    charts = DashboardCharts()
    curves = {
        "DMR-ML": state.result_ml.equity_curve,
        "DMR": state.result_base.equity_curve,
        "沪深300": state.bench,
    }
    fig = charts.create_drawdown(curves)
    return JSONResponse(content=json.loads(fig.to_json()))


@app.get("/api/chart/heatmap")
async def get_heatmap_chart(
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """月度收益热力图"""
    state.ensure_ready(momentum_window, ma_window)
    charts = DashboardCharts()
    fig = charts.create_monthly_heatmap(state.result_ml.equity_curve)
    return JSONResponse(content=json.loads(fig.to_json()))


@app.get("/api/chart/distribution")
async def get_distribution_chart(
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """收益分布图"""
    state.ensure_ready(momentum_window, ma_window)
    charts = DashboardCharts()
    fig = charts.create_return_distribution(state.result_ml.trades)
    return JSONResponse(content=json.loads(fig.to_json()))


@app.get("/api/chart/sharpe")
async def get_sharpe_chart(
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """滚动夏普比率图"""
    state.ensure_ready(momentum_window, ma_window)
    charts = DashboardCharts()
    curves = {
        "DMR-ML": state.result_ml.equity_curve,
        "DMR": state.result_base.equity_curve,
    }
    fig = charts.create_rolling_sharpe(curves)
    return JSONResponse(content=json.loads(fig.to_json()))


@app.get("/api/trades/summary")
async def get_trades_summary(
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """交易记录汇总"""
    state.ensure_ready(momentum_window, ma_window)
    analyzer = TradeAnalyzer(state.result_ml.trades)
    summary = analyzer.get_summary()
    allocation = analyzer.get_yearly_allocation()

    return json_response({
        "summary": summary,
        "allocation": allocation.to_dict('records') if not allocation.empty else [],
    })


@app.get("/api/chart/trade-signals")
async def get_trade_signals_chart(
    year: int = Query(2026),
    asset: str = Query("1000"),
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """交易信号可视化"""
    state.ensure_ready(momentum_window, ma_window)
    charts = DashboardCharts()

    if asset == "300":
        df_asset = state.df300
        target_asset = "300"
    else:
        df_asset = state.df1000
        target_asset = "1000"

    fig = charts.create_trade_signals(
        df=df_asset,
        trades=state.result_ml.trades,
        target_asset=target_asset,
        year=year,
        ma_window=ma_window,
    )
    return JSONResponse(content=json.loads(fig.to_json()))


@app.get("/api/trades/list")
async def get_trades_list(
    year: Optional[int] = Query(None),
    asset: Optional[str] = Query(None),
    momentum_window: int = Query(20), ma_window: int = Query(14),
):
    """交易记录列表"""
    state.ensure_ready(momentum_window, ma_window)
    trades = state.result_ml.trades

    result = []
    for t in trades:
        if year and not (t.entry_date.year == year or t.exit_date.year == year):
            continue
        if asset and t.asset != asset:
            continue
        result.append({
            "asset": "沪深300" if t.asset == "300" else "中证1000",
            "entry_date": t.entry_date.strftime('%Y-%m-%d'),
            "exit_date": t.exit_date.strftime('%Y-%m-%d'),
            "return_pct": t.return_pct,
            "holding_days": t.holding_days,
            "exit_reason": t.exit_reason,
        })

    return json_response({"trades": result, "total": len(result)})


# ============================================================
# 管理后台 API
# ============================================================

@app.get("/api/subscribe")
async def subscribe(
    email: str = Query(...),
    push_time: str = Query("08:00"),
    model: str = Query("adagio"),
):
    """邮箱订阅"""
    try:
        success, msg = subscribe_email(email, push_time, model)
        if success:
            # 尝试发送确认邮件
            try:
                sender = EmailSender()
                model_name = "Adagio" if model == "adagio" else "Presto"
                sender.send_welcome_email(email, push_time, model_name)
            except Exception:
                pass
        return json_response({"status": "ok" if success else "error", "message": msg})
    except Exception as e:
        return json_response({"status": "error", "message": str(e)})


@app.get("/api/unsubscribe")
async def unsubscribe(email: str = Query(...)):
    """用户自助取消订阅"""
    from subscription_service import unsubscribe_email
    try:
        success, msg = unsubscribe_email(email)
        return json_response({"status": "ok" if success else "error", "message": msg})
    except Exception as e:
        return json_response({"status": "error", "message": str(e)})


ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """管理后台页面"""
    html_path = TEMPLATES_DIR / "admin.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/admin/login")
async def admin_login(password: str = Query(...)):
    """管理员登录验证"""
    if password == ADMIN_PASSWORD:
        return json_response({"status": "ok"})
    return json_response({"status": "error", "message": "密码错误"})


@app.get("/api/admin/subscribers")
async def get_subscribers(password: str = Query(...)):
    """获取订阅者列表"""
    if password != ADMIN_PASSWORD:
        return json_response({"status": "error", "message": "未授权"})

    manager = SubscriptionManager()
    subscribers = load_subscribers()
    storage_info = manager.get_storage_info()

    result = []
    for sub in subscribers:
        result.append({
            "email": sub.email,
            "push_time": sub.push_time,
            "subscribe_time": sub.subscribe_time,
        })

    return json_response({
        "status": "ok",
        "storage_info": storage_info,
        "subscribers": result,
        "total": len(result),
    })


@app.get("/api/admin/delete-subscriber")
async def admin_delete_subscriber(
    password: str = Query(...),
    email: str = Query(...),
):
    """删除订阅者"""
    if password != ADMIN_PASSWORD:
        return json_response({"status": "error", "message": "未授权"})

    success, msg = delete_subscriber(email)
    return json_response({"status": "ok" if success else "error", "message": msg})
