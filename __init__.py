"""
DMR-ML
基于机器学习的双重动量轮动策略量化交易系统
Dual Momentum Rotation with Machine Learning

模块说明:
- config: 系统配置管理
- data_service: 数据服务层
- models: 策略和ML模型
- backtest_engine: 回测引擎
- reports: 报表生成
- visualization: Plotly可视化
- utils: 工具函数
- web: FastAPI 后端与前端

快速开始:
    $ cd DMR-ML
    $ pip install -r requirements.txt
    $ uvicorn web.api:app --host 0.0.0.0 --port 8000

Author: Kai
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "Kai"

from .config import get_config, SystemConfig
from .data_service import DataService, get_data_service
from .models import DMRStrategy, MLRiskModel, DMRMLStrategy
from .backtest_engine import BacktestEngine, BacktestResult
from .reports import ReportGenerator, SignalGenerator
from .visualization import DashboardCharts

__all__ = [
    "get_config",
    "SystemConfig",
    "DataService",
    "get_data_service",
    "DMRStrategy",
    "MLRiskModel",
    "DMRMLStrategy",
    "BacktestEngine",
    "BacktestResult",
    "ReportGenerator",
    "SignalGenerator",
    "DashboardCharts",
]
