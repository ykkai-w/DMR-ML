"""
DMR-ML - 工具函数模块
通用工具函数和辅助类

Author: Kai
"""

import os
import json
import pickle
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict, Callable, TypeVar
from functools import wraps
import pandas as pd
import numpy as np

T = TypeVar('T')


# 时区配置

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    """
    获取北京时间（无论服务器在哪个时区）
    
    适用于 GitHub Actions 与本地开发
    """
    return datetime.now(BEIJING_TZ)


# 日期工具

def is_trading_day(date: datetime = None) -> bool:
    """
    判断是否为交易日（简化版，仅排除周末）
    实际应用需要接入交易日历
    """
    if date is None:
        date = get_beijing_now()
    return date.weekday() < 5


def get_trading_status() -> Dict[str, Any]:
    """获取当前交易状态（基于北京时间）"""
    now = get_beijing_now()
    weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    
    is_weekend = now.weekday() >= 5
    hour = now.hour
    minute = now.minute
    
    if is_weekend:
        status = "休市（周末）"
        status_code = "closed"
    elif 9 <= hour < 11 or (hour == 11 and minute <= 30):
        status = "上午交易时段"
        status_code = "trading"
    elif (hour == 11 and minute > 30) or (hour == 12):
        status = "午间休市"
        status_code = "break"
    elif 13 <= hour < 15:
        status = "下午交易时段"
        status_code = "trading"
    else:
        status = "非交易时段"
        status_code = "closed"
    
    return {
        "datetime": now,
        "datetime_str": now.strftime('%Y-%m-%d %H:%M:%S'),
        "weekday": weekday_map[now.weekday()],
        "status": status,
        "status_code": status_code,
        "is_trading": status_code == "trading",
    }


def format_date(date: Any, fmt: str = '%Y-%m-%d') -> str:
    """格式化日期"""
    if isinstance(date, str):
        return date
    if isinstance(date, (pd.Timestamp, datetime)):
        return date.strftime(fmt)
    return str(date)


def parse_date(date_str: str, fmt: str = '%Y%m%d') -> datetime:
    """解析日期字符串"""
    return datetime.strptime(date_str, fmt)


# 数值格式化

def format_percent(value: float, decimals: int = 2) -> str:
    """格式化百分比"""
    return f"{value * 100:.{decimals}f}%"


def format_number(value: float, decimals: int = 2) -> str:
    """格式化数字"""
    return f"{value:,.{decimals}f}"


def format_currency(value: float, currency: str = "¥", decimals: int = 2) -> str:
    """格式化货币"""
    return f"{currency}{value:,.{decimals}f}"


def format_large_number(value: float) -> str:
    """格式化大数字（带单位）"""
    if abs(value) >= 1e12:
        return f"{value / 1e12:.2f}万亿"
    elif abs(value) >= 1e8:
        return f"{value / 1e8:.2f}亿"
    elif abs(value) >= 1e4:
        return f"{value / 1e4:.2f}万"
    else:
        return f"{value:.2f}"


# 性能计算工具

def calculate_cagr(start_value: float, end_value: float, years: float) -> float:
    """计算复合年化增长率"""
    if years <= 0 or start_value <= 0:
        return 0
    return (end_value / start_value) ** (1 / years) - 1


def calculate_sharpe(returns: pd.Series, risk_free_rate: float = 0.03) -> float:
    """计算夏普比率"""
    if returns.std() == 0:
        return 0
    excess_return = returns.mean() * 252 - risk_free_rate
    volatility = returns.std() * np.sqrt(252)
    return excess_return / volatility


def calculate_sortino(returns: pd.Series, risk_free_rate: float = 0.03) -> float:
    """计算索提诺比率"""
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0
    excess_return = returns.mean() * 252 - risk_free_rate
    downside_std = downside.std() * np.sqrt(252)
    return excess_return / downside_std


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """计算最大回撤"""
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax
    return drawdown.min()


def calculate_win_rate(returns: pd.Series) -> float:
    """计算胜率"""
    if len(returns) == 0:
        return 0
    return (returns > 0).sum() / len(returns)


# 缓存工具

class SimpleCache:
    """简单的内存缓存"""
    
    def __init__(self, max_size: int = 100):
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size
    
    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)
    
    def set(self, key: str, value: Any):
        if len(self._cache) >= self._max_size:
            # 简单的LRU：删除第一个
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = value
    
    def clear(self):
        self._cache.clear()
    
    def __contains__(self, key: str) -> bool:
        return key in self._cache


def memoize(func: Callable[..., T]) -> Callable[..., T]:
    """简单的记忆化装饰器"""
    cache = {}
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        key = str(args) + str(sorted(kwargs.items()))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    
    wrapper.cache_clear = lambda: cache.clear()
    return wrapper


def disk_cache(cache_dir: str = "./cache"):
    """磁盘缓存装饰器"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key_str = f"{func.__name__}_{str(args)}_{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(key_str.encode()).hexdigest()
            cache_path = os.path.join(cache_dir, f"{cache_key}.pkl")
            
            # 检查缓存
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'rb') as f:
                        return pickle.load(f)
                except:
                    pass
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 保存缓存
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(result, f)
            
            return result
        
        return wrapper
    return decorator


# 日志工具

class Logger:
    """简单的日志工具"""
    
    LEVELS = {
        'DEBUG': 10,
        'INFO': 20,
        'WARNING': 30,
        'ERROR': 40,
    }
    
    def __init__(self, name: str = "DMR_ML", level: str = "INFO"):
        self.name = name
        self.level = self.LEVELS.get(level.upper(), 20)
    
    def _log(self, level: str, message: str):
        if self.LEVELS.get(level, 0) >= self.level:
            timestamp = get_beijing_now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] [{level}] {self.name}: {message}")
    
    def debug(self, message: str):
        self._log('DEBUG', message)
    
    def info(self, message: str):
        self._log('INFO', message)
    
    def warning(self, message: str):
        self._log('WARNING', message)
    
    def error(self, message: str):
        self._log('ERROR', message)


# 全局日志实例
logger = Logger()


# 数据验证工具

def validate_dataframe(
    df: pd.DataFrame,
    required_columns: list,
    name: str = "DataFrame"
) -> bool:
    """验证 DataFrame 结构"""
    if df is None or df.empty:
        logger.error(f"{name} 为空")
        return False
    
    missing = set(required_columns) - set(df.columns)
    if missing:
        logger.error(f"{name} 缺少列: {missing}")
        return False
    
    return True


def validate_date_range(
    start_date: str,
    end_date: str,
) -> bool:
    """验证日期范围"""
    try:
        start = parse_date(start_date)
        end = parse_date(end_date)
        if start >= end:
            logger.error("开始日期必须早于结束日期")
            return False
        return True
    except Exception as e:
        logger.error(f"日期格式错误: {e}")
        return False


# 指标卡片生成

def create_metric_card(
    label: str,
    value: Any,
    delta: Optional[float] = None,
    delta_color: str = "normal",
    prefix: str = "",
    suffix: str = "",
) -> Dict[str, Any]:
    """
    创建指标卡片数据
    用于指标卡片组件
    """
    return {
        "label": label,
        "value": f"{prefix}{value}{suffix}",
        "delta": delta,
        "delta_color": delta_color,
    }


def format_metrics_for_display(metrics: Dict[str, float]) -> Dict[str, str]:
    """格式化指标用于显示"""
    formatters = {
        'total_return': lambda x: format_percent(x),
        'annual_return': lambda x: format_percent(x),
        'max_drawdown': lambda x: format_percent(x),
        'sharpe_ratio': lambda x: f"{x:.2f}",
        'sortino_ratio': lambda x: f"{x:.2f}",
        'calmar_ratio': lambda x: f"{x:.2f}",
        'volatility': lambda x: format_percent(x),
        'win_rate': lambda x: format_percent(x),
        'profit_loss_ratio': lambda x: f"{x:.2f}",
    }
    
    result = {}
    for key, value in metrics.items():
        formatter = formatters.get(key, lambda x: str(x))
        result[key] = formatter(value)
    
    return result


# 表格工具

def style_dataframe(
    df: pd.DataFrame,
    percent_columns: list = None,
    highlight_columns: list = None,
) -> pd.DataFrame:
    """
    样式化 DataFrame
    """
    styled = df.copy()
    
    # 百分比列格式化
    if percent_columns:
        for col in percent_columns:
            if col in styled.columns:
                styled[col] = styled[col].apply(lambda x: format_percent(x) if pd.notna(x) else '-')
    
    return styled


# 颜色工具

def get_trend_color(value: float, positive_is_good: bool = True) -> str:
    """根据数值获取趋势颜色"""
    if value > 0:
        return "#43A047" if positive_is_good else "#D32F2F"  # 绿/红
    elif value < 0:
        return "#D32F2F" if positive_is_good else "#43A047"  # 红/绿
    else:
        return "#9B9B9B"  # 灰


def get_risk_color(value: float, thresholds: tuple = (0.33, 0.40)) -> str:
    """根据风险值获取颜色"""
    low, high = thresholds
    if value < low:
        return "#43A047"  # 绿色（安全）
    elif value < high:
        return "#F39C12"  # 黄色（警告）
    else:
        return "#D32F2F"  # 红色（危险）
