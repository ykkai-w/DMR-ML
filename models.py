"""
DMR-ML - 策略模型模块
包含 DMR 双重动量策略和 ML 风险模型

Author: Kai
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, List, Dict
from sklearn.ensemble import RandomForestClassifier
from dataclasses import dataclass, field

from config import get_config
from data_service import FeatureEngineer


@dataclass
class Signal:
    """交易信号数据类"""
    date: pd.Timestamp
    position: str           # "300", "1000", "CASH"
    momentum_300: float     # 沪深300动量
    momentum_1000: float    # 中证1000动量
    ma_300: float           # 沪深300均线值
    ma_1000: float          # 中证1000均线值
    signal_300: bool        # 沪深300信号
    signal_1000: bool       # 中证1000信号
    ml_risk_prob: Optional[float] = None  # ML风险概率
    risk_off: bool = False  # 是否处于避险模式
    reason: str = ""        # 决策原因


class DMRStrategy:
    """
    DMR 双重动量轮动策略
    
    策略逻辑:
    1. 相对动量：比较两个资产的涨跌幅，选择强势方
    2. 绝对动量：价格高于均线且动量为正时入场
    3. 双阈值迟滞：配合ML模块减少频繁切换
    """
    
    def __init__(
        self,
        momentum_window: int = 20,
        ma_window: int = 14,
    ):
        """
        Parameters:
        -----------
        momentum_window : int
            动量计算窗口
        ma_window : int
            均线计算窗口
        """
        self.config = get_config()
        self.momentum_window = momentum_window
        self.ma_window = ma_window
        self.warmup_period = max(momentum_window, ma_window) + 1
        
    def compute_momentum(self, prices: pd.Series, window: int) -> pd.Series:
        """
        计算动量指标
        
        Parameters:
        -----------
        prices : pd.Series
            价格序列
        window : int
            计算窗口
            
        Returns:
        --------
        pd.Series
            动量序列 (当前价格/前n日价格 - 1)
        """
        return prices / prices.shift(window + 1) - 1
    
    def compute_ma(self, prices: pd.Series, window: int) -> pd.Series:
        """
        计算移动平均线
        
        Parameters:
        -----------
        prices : pd.Series
            价格序列
        window : int
            均线窗口
            
        Returns:
        --------
        pd.Series
            均线序列
        """
        return prices.rolling(window=window).mean()
    
    def generate_signal(
        self,
        price_300: float,
        price_1000: float,
        momentum_300: float,
        momentum_1000: float,
        ma_300: float,
        ma_1000: float,
    ) -> Tuple[str, str]:
        """
        生成交易信号
        
        Parameters:
        -----------
        price_300 : float
            沪深300当前价格
        price_1000 : float
            中证1000当前价格
        momentum_300 : float
            沪深300动量
        momentum_1000 : float
            中证1000动量
        ma_300 : float
            沪深300均线值
        ma_1000 : float
            中证1000均线值
            
        Returns:
        --------
        Tuple[str, str]
            (目标仓位, 决策原因)
        """
        # 计算绝对动量信号
        sig_300 = (price_300 > ma_300) and (momentum_300 > 0)
        sig_1000 = (price_1000 > ma_1000) and (momentum_1000 > 0)
        
        # 决策逻辑
        if sig_300 and sig_1000:
            # 两者都是多头，选择更强的
            if momentum_300 > momentum_1000:
                return "300", "两指数均多头，大盘更强"
            else:
                return "1000", "两指数均多头，小盘更强"
        elif sig_300:
            return "300", "大盘多头，小盘走弱"
        elif sig_1000:
            return "1000", "小盘多头，大盘走弱"
        else:
            return "CASH", "无有效信号"
    
    def run(
        self, 
        df300: pd.DataFrame, 
        df1000: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[Signal]]:
        """
        运行策略（不含ML）
        
        Parameters:
        -----------
        df300 : pd.DataFrame
            沪深300数据
        df1000 : pd.DataFrame
            中证1000数据
            
        Returns:
        --------
        Tuple[pd.DataFrame, List[Signal]]
            (指标数据, 信号列表)
        """
        # 对齐数据
        common_idx = df300.index.intersection(df1000.index)
        d300 = df300.loc[common_idx].copy()
        d1000 = df1000.loc[common_idx].copy()
        
        # 计算指标
        d300['momentum'] = self.compute_momentum(d300['close'], self.momentum_window)
        d1000['momentum'] = self.compute_momentum(d1000['close'], self.momentum_window)
        d300['ma'] = self.compute_ma(d300['close'], self.ma_window)
        d1000['ma'] = self.compute_ma(d1000['close'], self.ma_window)
        
        # 生成信号
        signals = []
        for i in range(self.warmup_period, len(common_idx)):
            date = common_idx[i]
            p300, p1000 = d300['close'].iloc[i], d1000['close'].iloc[i]
            m300, m1000 = d300['momentum'].iloc[i], d1000['momentum'].iloc[i]
            ma300, ma1000 = d300['ma'].iloc[i], d1000['ma'].iloc[i]
            
            position, reason = self.generate_signal(p300, p1000, m300, m1000, ma300, ma1000)
            sig_300 = (p300 > ma300) and (m300 > 0)
            sig_1000 = (p1000 > ma1000) and (m1000 > 0)
            
            signals.append(Signal(
                date=date,
                position=position,
                momentum_300=m300,
                momentum_1000=m1000,
                ma_300=ma300,
                ma_1000=ma1000,
                signal_300=sig_300,
                signal_1000=sig_1000,
                reason=reason
            ))
        
        # 合并指标数据
        result = pd.DataFrame({
            'close_300': d300['close'],
            'close_1000': d1000['close'],
            'momentum_300': d300['momentum'],
            'momentum_1000': d1000['momentum'],
            'ma_300': d300['ma'],
            'ma_1000': d1000['ma'],
        }, index=common_idx)
        
        return result, signals


class MLRiskModel:
    """
    机器学习风险识别模型
    
    使用随机森林分类器识别市场高风险时段
    采用 Purged Walk-forward 滚动训练防止标签泄露
    """
    
    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 5,
        min_samples_leaf: int = 15,
        random_state: int = 42,
    ):
        """
        Parameters:
        -----------
        n_estimators : int
            决策树数量
        max_depth : int
            最大深度
        min_samples_leaf : int
            叶节点最小样本数
        random_state : int
            随机种子
        """
        self.config = get_config()
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        
        self.model: Optional[RandomForestClassifier] = None
        self.feature_importance_: Optional[pd.Series] = None
        self.risk_probs_: Optional[pd.Series] = None
        
    def _create_model(self) -> RandomForestClassifier:
        """创建随机森林模型实例"""
        return RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            class_weight='balanced'
        )
    
    def fit_predict(
        self,
        df: pd.DataFrame,
        features: Optional[List[str]] = None,
        train_window: int = 252,
        horizon: int = 5,
        step: int = 20,
        verbose: bool = True
    ) -> pd.Series:
        """
        使用 Purged Walk-forward 方式训练并生成风险概率
        
        Parameters:
        -----------
        df : pd.DataFrame
            输入数据（需要包含特征列和标签列）
        features : List[str], optional
            特征列列表
        train_window : int
            训练窗口大小
        horizon : int
            预测时间窗口（也用于构建标签和隔离带）
        step : int
            滚动步长
        verbose : bool
            是否打印进度
            
        Returns:
        --------
        pd.Series
            风险概率序列
        """
        if features is None:
            features = self.config.ml.features
        
        if verbose:
            print("\n>>> 正在训练机器学习风险识别模型...")
        
        # 准备数据
        fe = FeatureEngineer(df)
        fe.compute_all_features().compute_risk_label(horizon=horizon)
        data = fe.get_result()
        
        # 初始化风险概率序列
        risk_probs = pd.Series(0.0, index=data.index)
        
        # 记录特征重要性
        all_importances = []
        
        # Purged Walk-forward 滚动训练
        total_steps = (len(data) - train_window - horizon - horizon) // step + 1
        current_step = 0
        
        for t in range(train_window + horizon, len(data) - horizon, step):
            current_step += 1
            
            # 训练集：[t-train_window, t-horizon)，留出隔离带防止标签泄露
            train_df = data.iloc[t - train_window: t - horizon].dropna()
            
            # 检查训练数据质量
            if len(train_df) < 100 or len(np.unique(train_df['label'])) < 2:
                continue
            
            X_train = train_df[features]
            y_train = train_df['label']
            
            # 训练模型
            model = self._create_model()
            model.fit(X_train, y_train)
            
            # 记录特征重要性
            all_importances.append(dict(zip(features, model.feature_importances_)))
            
            # 预测测试集
            X_test = data.iloc[t: t + step][features].fillna(0)
            risk_probs.iloc[t: t + step] = model.predict_proba(X_test)[:, 1]
            
            if verbose and current_step % 10 == 0:
                print(f"  训练进度: {current_step}/{total_steps}")
        
        # 平滑处理
        self.risk_probs_ = risk_probs.ewm(span=5).mean()
        
        # 汇总特征重要性
        if all_importances:
            importance_df = pd.DataFrame(all_importances)
            self.feature_importance_ = importance_df.mean().sort_values(ascending=False)
        
        # 保存最后一个模型
        self.model = model
        
        if verbose:
            print(">>> 模型训练完成")
            if self.feature_importance_ is not None:
                print("\n特征重要性:")
                for feat, imp in self.feature_importance_.items():
                    print(f"  {feat}: {imp:.4f}")
        
        return self.risk_probs_
    
    def get_risk_signal(
        self,
        current_prob: float,
        is_risk_off: bool,
        trigger_threshold: Optional[float] = None,
        release_threshold: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        获取风险信号（双阈值迟滞机制）
        
        Parameters:
        -----------
        current_prob : float
            当前风险概率
        is_risk_off : bool
            当前是否处于避险模式
        trigger_threshold : float, optional
            触发阈值
        release_threshold : float, optional
            解除阈值
            
        Returns:
        --------
        Tuple[bool, str]
            (是否避险, 信号说明)
        """
        trigger = trigger_threshold or self.config.ml.risk_trigger_threshold
        release = release_threshold or self.config.ml.risk_release_threshold
        
        if not is_risk_off and current_prob > trigger:
            return True, f"风险概率 {current_prob:.1%} 超过触发阈值 {trigger:.0%}，进入避险"
        elif is_risk_off and current_prob < release:
            return False, f"风险概率 {current_prob:.1%} 低于解除阈值 {release:.0%}，解除避险"
        else:
            if is_risk_off:
                return True, f"风险概率 {current_prob:.1%}，维持避险状态"
            else:
                return False, f"风险概率 {current_prob:.1%}，正常交易"


class DMRMLStrategy:
    """
    DMR-ML 组合策略
    
    整合 DMR 双重动量策略和 ML 风险识别模型
    """
    
    def __init__(
        self,
        momentum_window: int = 20,
        ma_window: int = 14,
        ml_config: Optional[Dict] = None,
    ):
        """
        Parameters:
        -----------
        momentum_window : int
            动量计算窗口
        ma_window : int
            均线计算窗口
        ml_config : Dict, optional
            ML模型配置
        """
        self.config = get_config()
        self.momentum_window = momentum_window
        self.ma_window = ma_window
        
        # 初始化子模块
        self.dmr = DMRStrategy(momentum_window, ma_window)
        
        ml_params = ml_config or {}
        self.ml = MLRiskModel(**ml_params)
        
        # 状态
        self.is_trained = False
        self.risk_probs: Optional[pd.Series] = None
    
    def train_ml_model(self, df300: pd.DataFrame, verbose: bool = True):
        """
        训练 ML 风险模型
        
        Parameters:
        -----------
        df300 : pd.DataFrame
            沪深300数据（用于训练）
        verbose : bool
            是否打印进度
        """
        self.risk_probs = self.ml.fit_predict(
            df300,
            train_window=self.config.ml.train_window,
            horizon=self.config.ml.horizon,
            step=self.config.ml.step,
            verbose=verbose
        )
        self.is_trained = True
    
    def generate_signals(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
    ) -> List[Signal]:
        """
        生成交易信号（含ML风险过滤）
        
        Parameters:
        -----------
        df300 : pd.DataFrame
            沪深300数据
        df1000 : pd.DataFrame
            中证1000数据
            
        Returns:
        --------
        List[Signal]
            信号列表
        """
        # 获取DMR信号
        _, dmr_signals = self.dmr.run(df300, df1000)
        
        if not self.is_trained or self.risk_probs is None:
            return dmr_signals
        
        # 应用ML风险过滤
        risk_off = False
        ml_signals = []
        
        for sig in dmr_signals:
            if sig.date in self.risk_probs.index:
                prob = self.risk_probs.loc[sig.date]
            else:
                prob = 0.0
            
            # 更新风险状态
            risk_off, ml_reason = self.ml.get_risk_signal(prob, risk_off)
            
            # 创建新信号
            new_sig = Signal(
                date=sig.date,
                position=sig.position if not risk_off else "CASH",
                momentum_300=sig.momentum_300,
                momentum_1000=sig.momentum_1000,
                ma_300=sig.ma_300,
                ma_1000=sig.ma_1000,
                signal_300=sig.signal_300,
                signal_1000=sig.signal_1000,
                ml_risk_prob=prob,
                risk_off=risk_off,
                reason=ml_reason if risk_off else sig.reason
            )
            ml_signals.append(new_sig)
        
        return ml_signals
    
    def get_latest_signal(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
    ) -> Signal:
        """
        获取最新交易信号
        
        Parameters:
        -----------
        df300 : pd.DataFrame
            沪深300数据
        df1000 : pd.DataFrame
            中证1000数据
            
        Returns:
        --------
        Signal
            最新信号
        """
        signals = self.generate_signals(df300, df1000)
        return signals[-1] if signals else None
