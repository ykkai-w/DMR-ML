"""
DMR-ML - 数据服务层
负责数据获取、缓存、预处理

Author: Kai
"""

import os
import pandas as pd
import numpy as np
import tushare as ts
from typing import Optional, Dict, Tuple
from datetime import datetime

from config import get_config


class DataService:
    """
    数据服务类
    提供统一的数据访问接口
    """
    
    def __init__(self):
        self.config = get_config()
        self._pro_api = None
        self._data_cache: Dict[str, pd.DataFrame] = {}
        
    @property
    def pro_api(self):
        """懒加载 Tushare API"""
        if self._pro_api is None:
            ts.set_token(self.config.tushare.token)
            self._pro_api = ts.pro_api()
        return self._pro_api
    
    def _get_cache_path(self, ts_code: str) -> str:
        """获取缓存文件路径"""
        cache_dir = self.config.cache.cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        return os.path.join(cache_dir, f"{ts_code}.pkl")
    
    def fetch_index_data(
        self, 
        ts_code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取指数日线数据
        
        Parameters:
        -----------
        ts_code : str
            指数代码 (如 '000300.SH')
        start_date : str, optional
            开始日期 (格式: YYYYMMDD)
        end_date : str, optional
            结束日期 (格式: YYYYMMDD)
        use_cache : bool
            是否使用缓存
            
        Returns:
        --------
        pd.DataFrame
            指数日线数据，index为trade_date
        """
        start = start_date or self.config.date.start_date
        end = end_date or self.config.date.end_date
        
        # 检查内存缓存
        cache_key = f"{ts_code}_{start}_{end}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key].copy()
        
        # 检查磁盘缓存
        cache_path = self._get_cache_path(ts_code)
        if use_cache and self.config.cache.enable_cache and os.path.exists(cache_path):
            try:
                df = pd.read_pickle(cache_path)
                if not df.empty and df.index[-1].strftime('%Y%m%d') >= end:
                    # 筛选日期范围
                    mask = (df.index >= pd.to_datetime(start)) & (df.index <= pd.to_datetime(end))
                    result = df.loc[mask].copy()
                    self._data_cache[cache_key] = result
                    return result
            except Exception:
                pass
        
        # 从API获取数据
        try:
            df = self.pro_api.index_daily(ts_code=ts_code, start_date=start, end_date=end)
            df = df.sort_values('trade_date')
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df.set_index('trade_date', inplace=True)
            
            # 保存缓存
            if self.config.cache.enable_cache:
                df.to_pickle(cache_path)
            
            self._data_cache[cache_key] = df
            print(f"[{ts_code}] 数据同步完成: {len(df)} 条记录")
            return df
            
        except Exception as e:
            print(f"[{ts_code}] 数据获取异常: {e}")
            return pd.DataFrame()
    
    def get_csi300(self, **kwargs) -> pd.DataFrame:
        """获取沪深300数据"""
        return self.fetch_index_data(self.config.asset.csi300_code, **kwargs)
    
    def get_csi1000(self, **kwargs) -> pd.DataFrame:
        """获取中证1000数据"""
        return self.fetch_index_data(self.config.asset.csi1000_code, **kwargs)
    
    def get_aligned_data(self, **kwargs) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        获取对齐后的双指数数据
        
        Returns:
        --------
        Tuple[pd.DataFrame, pd.DataFrame]
            (沪深300数据, 中证1000数据) - 已对齐日期
        """
        df300 = self.get_csi300(**kwargs)
        df1000 = self.get_csi1000(**kwargs)
        
        # 对齐日期
        common_dates = df300.index.intersection(df1000.index)
        df300 = df300.loc[common_dates].copy()
        df1000 = df1000.loc[common_dates].copy()
        
        return df300, df1000
    
    def clear_cache(self):
        """清除所有缓存"""
        self._data_cache.clear()
        cache_dir = self.config.cache.cache_dir
        if os.path.exists(cache_dir):
            import shutil
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir)
        print("缓存已清除")


class FeatureEngineer:
    """
    特征工程类
    为机器学习模型构建特征
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        Parameters:
        -----------
        df : pd.DataFrame
            原始数据，需要包含 close, vol, pct_chg 列
        """
        self.df = df.copy()
        self.config = get_config()
        
    def compute_returns(self) -> 'FeatureEngineer':
        """计算日收益率"""
        self.df['ret'] = self.df['pct_chg'] / 100.0
        return self
    
    def compute_volatility_ratio(self, short_window: int = 5, long_window: int = 20) -> 'FeatureEngineer':
        """
        计算波动率比值
        短期波动率 / 长期波动率
        """
        self.df['vol_ratio'] = (
            self.df['ret'].rolling(short_window).std() / 
            self.df['ret'].rolling(long_window).std()
        )
        return self
    
    def compute_ma_bias(self, window: int = 20) -> 'FeatureEngineer':
        """
        计算均线乖离率
        (现价 - 均线) / 均线
        """
        self.df['ma_bias'] = (
            self.df['close'] / self.df['close'].rolling(window).mean() - 1
        )
        return self
    
    def compute_volume_factor(self, window: int = 20) -> 'FeatureEngineer':
        """
        计算成交量异动因子
        当前成交量 / 均量
        """
        self.df['vol_factor'] = (
            self.df['vol'] / self.df['vol'].rolling(window).mean()
        )
        return self
    
    def compute_volume_volatility(self, window: int = 20) -> 'FeatureEngineer':
        """
        计算成交量波动率
        成交量标准差 / 成交量均值
        """
        self.df['vol_std'] = (
            self.df['vol'].rolling(window).std() / 
            self.df['vol'].rolling(window).mean()
        )
        return self
    
    def compute_price_volume_corr(self, window: int = 20) -> 'FeatureEngineer':
        """
        计算价量相关系数
        """
        self.df['pv_corr'] = (
            self.df['close'].rolling(window).corr(self.df['vol'])
        )
        return self
    
    def compute_return_autocorr(self, window: int = 20, lag: int = 1) -> 'FeatureEngineer':
        """
        计算收益率自相关
        """
        self.df['ret_lag1'] = self.df['ret'].shift(lag)
        self.df['ret_autocorr'] = (
            self.df['ret'].rolling(window).corr(self.df['ret_lag1'])
        )
        return self
    
    def compute_volatility_regime(self, short_window: int = 5) -> 'FeatureEngineer':
        """
        计算波动率状态变化
        当前波动率 / 前一期波动率
        """
        vol_5 = self.df['ret'].rolling(short_window).std()
        self.df['vol_regime'] = vol_5 / vol_5.shift(short_window)
        return self
    
    def compute_risk_label(self, horizon: int = 5, threshold: float = -0.025) -> 'FeatureEngineer':
        """
        构建风险标签
        未来horizon日最大跌幅超过threshold则为高风险
        """
        future_min = self.df['ret'].shift(-horizon).rolling(horizon).min()
        self.df['label'] = (future_min < threshold).astype(int)
        return self
    
    def compute_all_features(self) -> 'FeatureEngineer':
        """
        计算所有特征
        """
        return (
            self.compute_returns()
            .compute_volatility_ratio()
            .compute_ma_bias()
            .compute_volume_factor()
            .compute_volume_volatility()
            .compute_price_volume_corr()
            .compute_return_autocorr()
            .compute_volatility_regime()
        )
    
    def get_features(self, feature_list: Optional[list] = None) -> pd.DataFrame:
        """
        获取特征数据
        
        Parameters:
        -----------
        feature_list : list, optional
            特征列表，默认使用配置中的特征
            
        Returns:
        --------
        pd.DataFrame
            特征数据框
        """
        if feature_list is None:
            feature_list = self.config.ml.features
        
        return self.df[feature_list].copy()
    
    def get_result(self) -> pd.DataFrame:
        """获取完整结果数据"""
        return self.df.copy()


# 全局数据服务实例
_data_service_instance = None


def get_data_service() -> DataService:
    """获取数据服务单例"""
    global _data_service_instance
    if _data_service_instance is None:
        _data_service_instance = DataService()
    return _data_service_instance
