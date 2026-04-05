"""
DMR-ML - 配置管理模块
集中管理所有系统配置参数，支持环境变量覆盖

Author: Kai
"""

import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import List, Tuple

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    """获取北京时间"""
    return datetime.now(BEIJING_TZ)


@dataclass
class TushareConfig:
    """Tushare API 配置"""
    token: str = field(default_factory=lambda: os.environ.get("TUSHARE_TOKEN", ""))


@dataclass
class DateConfig:
    """日期配置"""
    start_date: str = "20190101"
    end_date: str = field(default_factory=lambda: get_beijing_now().strftime('%Y%m%d'))


@dataclass
class TradingConfig:
    """交易参数配置"""
    # 交易成本
    commission_rate: float = 0.0003          # 单边手续费率
    slippage: float = 0.0001                 # 滑点估计
    
    # 风险管理
    risk_free_rate: float = 0.03             # 无风险利率（年化）
    max_drawdown_limit: float = -0.20        # 最大回撤限制
    
    @property
    def daily_rf(self) -> float:
        """日化无风险收益率"""
        return self.risk_free_rate / 252


@dataclass
class StrategyConfig:
    """策略参数配置"""
    # 动量参数搜索范围
    momentum_range: Tuple[int, int, int] = (15, 31, 5)  # (start, stop, step)
    
    # 均线参数搜索范围
    ma_range: Tuple[int, int, int] = (10, 21, 2)        # (start, stop, step)
    
    # 默认参数（优化前使用）
    default_momentum_window: int = 20
    default_ma_window: int = 14
    
    @property
    def mom_range_list(self) -> List[int]:
        """返回动量参数列表"""
        return list(range(*self.momentum_range))
    
    @property
    def ma_range_list(self) -> List[int]:
        """返回均线参数列表"""
        return list(range(*self.ma_range))


@dataclass
class MLConfig:
    """机器学习模块配置"""
    # 风险阈值（双阈值迟滞机制）
    risk_trigger_threshold: float = 0.40     # 触发避险阈值
    risk_release_threshold: float = 0.33     # 解除避险阈值
    
    # 模型参数
    train_window: int = 252                   # 训练窗口（交易日）
    horizon: int = 5                          # 预测时间窗口
    step: int = 20                            # 滚动步长
    
    # 随机森林参数
    n_estimators: int = 100                   # 决策树数量
    max_depth: int = 5                        # 最大深度
    min_samples_leaf: int = 15                # 叶节点最小样本数
    random_state: int = 42                    # 随机种子
    
    # 标签构建
    risk_return_threshold: float = -0.025    # 风险收益阈值（-2.5%）
    
    # 特征列表
    features: List[str] = field(default_factory=lambda: [
        'vol_ratio',    # 短期/长期波动率比值
        'ma_bias',      # 均线乖离率
        'vol_factor',   # 成交量异动因子
    ])
    
    # 扩展特征（可选）
    extended_features: List[str] = field(default_factory=lambda: [
        'vol_std',      # 成交量波动率
        'pv_corr',      # 价量相关系数
        'ret_autocorr', # 收益率自相关
        'vol_regime',   # 波动率状态变化
    ])


@dataclass
class AssetConfig:
    """资产配置"""
    # 沪深300
    csi300_code: str = "000300.SH"
    csi300_name: str = "沪深300"
    
    # 中证1000
    csi1000_code: str = "000852.SH"
    csi1000_name: str = "中证1000"


@dataclass  
class CacheConfig:
    """缓存配置"""
    cache_dir: str = "./cache"
    enable_cache: bool = True


@dataclass
class UIConfig:
    """界面配置"""
    # 主题配色
    primary_color: str = "#C7302A"       # 主色（深红）
    secondary_color: str = "#4A90E2"     # 次色（深蓝）
    neutral_color: str = "#9B9B9B"       # 中性色（灰）
    success_color: str = "#43A047"       # 成功色（绿）
    warning_color: str = "#F39C12"       # 警告色（金）
    danger_color: str = "#D32F2F"        # 危险色（红）
    
    # 图表尺寸
    chart_width: int = 1200
    chart_height: int = 600
    
    # 页面配置
    page_title: str = "DMR-ML 机器学习量化交易系统"
    page_icon: str = "📈"
    layout: str = "wide"


class SystemConfig:
    """
    系统主配置类
    整合所有子配置模块
    """
    def __init__(self):
        self.tushare = TushareConfig()
        self.date = DateConfig()
        self.trading = TradingConfig()
        self.strategy = StrategyConfig()
        self.ml = MLConfig()
        self.asset = AssetConfig()
        self.cache = CacheConfig()
        self.ui = UIConfig()
    
    def to_dict(self) -> dict:
        """导出所有配置为字典"""
        return {
            "tushare": self.tushare.__dict__,
            "date": self.date.__dict__,
            "trading": self.trading.__dict__,
            "strategy": {
                **self.strategy.__dict__,
                "mom_range_list": self.strategy.mom_range_list,
                "ma_range_list": self.strategy.ma_range_list,
            },
            "ml": self.ml.__dict__,
            "asset": self.asset.__dict__,
            "cache": self.cache.__dict__,
            "ui": self.ui.__dict__,
        }
    
    def __repr__(self):
        return f"SystemConfig(start={self.date.start_date}, end={self.date.end_date})"


# 全局配置实例（单例模式）
_config_instance = None


def get_config() -> SystemConfig:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = SystemConfig()
    return _config_instance


def reset_config() -> SystemConfig:
    """重置配置实例"""
    global _config_instance
    _config_instance = SystemConfig()
    return _config_instance


# 便捷访问
CONFIG = get_config()

