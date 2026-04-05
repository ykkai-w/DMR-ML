"""
DMR-ML - 回测引擎
回测框架，支持多策略对比

Author: Kai
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from config import get_config
from models import DMRStrategy, MLRiskModel, Signal


@dataclass
class Trade:
    """交易记录"""
    asset: str               # "300" 或 "1000"
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_value: float       # 入场净值
    exit_value: float        # 出场净值
    return_pct: float        # 收益率
    holding_days: int        # 持仓天数
    exit_reason: str = ""    # 出场原因


@dataclass
class BacktestResult:
    """回测结果"""
    # 净值曲线
    equity_curve: pd.Series
    
    # 交易记录
    trades: List[Trade]
    
    # 核心指标
    total_return: float           # 累计收益
    annual_return: float          # 年化收益
    max_drawdown: float           # 最大回撤
    sharpe_ratio: float           # 夏普比率
    sortino_ratio: float          # 索提诺比率
    win_rate: float               # 胜率
    profit_loss_ratio: float      # 盈亏比
    
    # 交易统计
    total_trades: int             # 总交易次数
    winning_trades: int           # 盈利次数
    losing_trades: int            # 亏损次数
    avg_holding_days: float       # 平均持仓天数
    
    # 元信息
    strategy_name: str = ""
    momentum_window: int = 0
    ma_window: int = 0
    start_date: Optional[pd.Timestamp] = None
    end_date: Optional[pd.Timestamp] = None


class BacktestEngine:
    """
    回测引擎
    
    支持:
    - DMR 策略回测
    - DMR-ML 策略回测
    - 参数优化
    - 多策略对比
    """
    
    def __init__(self):
        self.config = get_config()
        
    def run_backtest(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
        momentum_window: int,
        ma_window: int,
        ml_probs: Optional[pd.Series] = None,
        strategy_name: str = "DMR",
    ) -> BacktestResult:
        """
        执行策略回测
        
        Parameters:
        -----------
        df300 : pd.DataFrame
            沪深300数据
        df1000 : pd.DataFrame
            中证1000数据
        momentum_window : int
            动量窗口
        ma_window : int
            均线窗口
        ml_probs : pd.Series, optional
            ML风险概率序列（传入则启用ML风控）
        strategy_name : str
            策略名称
            
        Returns:
        --------
        BacktestResult
            回测结果
        """
        # 对齐数据
        common_idx = df300.index.intersection(df1000.index)
        d300 = df300.loc[common_idx].copy()
        d1000 = df1000.loc[common_idx].copy()
        
        n = len(common_idx)
        curve = np.ones(n)
        pos = "CASH"
        warmup = max(momentum_window, ma_window) + 1
        
        # 交易记录
        trades: List[Trade] = []
        entry_date = None
        entry_val = 0.0
        risk_off = False
        
        # 配置参数
        commission = self.config.trading.commission_rate
        daily_rf = self.config.trading.daily_rf
        ml_trigger = self.config.ml.risk_trigger_threshold
        ml_release = self.config.ml.risk_release_threshold
        
        for i in range(warmup, n):
            current_date = common_idx[i]
            
            # 收益结算
            if pos == "300":
                day_ret = d300['pct_chg'].iloc[i] / 100.0
            elif pos == "1000":
                day_ret = d1000['pct_chg'].iloc[i] / 100.0
            else:
                day_ret = daily_rf
            
            curve[i] = curve[i - 1] * (1 + day_ret)
            
            # 信号计算
            p300 = d300['close'].iloc[i]
            p1000 = d1000['close'].iloc[i]
            
            m300 = p300 / d300['close'].iloc[i - momentum_window - 1] - 1
            m1000 = p1000 / d1000['close'].iloc[i - momentum_window - 1] - 1
            
            ma300_val = d300['close'].iloc[i - ma_window + 1: i + 1].mean()
            ma1000_val = d1000['close'].iloc[i - ma_window + 1: i + 1].mean()
            
            sig300 = (p300 > ma300_val) and (m300 > 0)
            sig1000 = (p1000 > ma1000_val) and (m1000 > 0)
            
            # 目标仓位
            target = "CASH"
            if sig300 and sig1000:
                target = "300" if m300 > m1000 else "1000"
            elif sig300:
                target = "300"
            elif sig1000:
                target = "1000"
            
            # ML风险门禁
            exit_reason = ""
            if ml_probs is not None and current_date in ml_probs.index:
                p_risk = ml_probs.loc[current_date]
                if not risk_off and p_risk > ml_trigger:
                    risk_off = True
                    exit_reason = f"ML风险触发({p_risk:.1%})"
                elif risk_off and p_risk < ml_release:
                    risk_off = False
                
                if risk_off:
                    target = "CASH"
            
            # 交易执行
            if target != pos:
                cost_mult = 2.0 if (pos != "CASH" and target != "CASH") else 1.0
                
                # 记录平仓交易
                if pos != "CASH" and entry_date is not None:
                    trade_ret = curve[i] / entry_val - 1
                    trades.append(Trade(
                        asset=pos,
                        entry_date=entry_date,
                        exit_date=current_date,
                        entry_value=entry_val,
                        exit_value=curve[i],
                        return_pct=trade_ret,
                        holding_days=(current_date - entry_date).days,
                        exit_reason=exit_reason or "信号切换"
                    ))
                
                # 记录开仓信息
                if target != "CASH":
                    entry_date = current_date
                    entry_val = curve[i] * (1 - commission * cost_mult)
                
                # 扣除交易成本
                curve[i] *= (1 - commission * cost_mult)
            
            pos = target
        
        # 构建净值序列
        equity_curve = pd.Series(curve, index=common_idx)
        
        # 计算指标
        metrics = self._calculate_metrics(equity_curve, trades)
        
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            strategy_name=strategy_name,
            momentum_window=momentum_window,
            ma_window=ma_window,
            start_date=common_idx[warmup],
            end_date=common_idx[-1],
            **metrics
        )
    
    def _calculate_metrics(
        self, 
        equity_curve: pd.Series, 
        trades: List[Trade]
    ) -> Dict[str, Any]:
        """计算回测指标"""
        
        # 基本收益指标
        total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        annual_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0
        
        # 风险指标
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # 日收益指标
        daily_ret = equity_curve.pct_change().dropna()
        risk_free = self.config.trading.risk_free_rate
        
        # 夏普比率
        if daily_ret.std() > 0:
            sharpe_ratio = (daily_ret.mean() * 252 - risk_free) / (daily_ret.std() * np.sqrt(252))
        else:
            sharpe_ratio = 0
        
        # 索提诺比率
        downside_ret = daily_ret[daily_ret < 0]
        if len(downside_ret) > 0 and downside_ret.std() > 0:
            downside_std = downside_ret.std() * np.sqrt(252)
            sortino_ratio = (daily_ret.mean() * 252 - risk_free) / downside_std
        else:
            sortino_ratio = 0
        
        # 交易指标
        total_trades = len(trades)
        if total_trades > 0:
            winning_trades = sum(1 for t in trades if t.return_pct > 0)
            losing_trades = total_trades - winning_trades
            win_rate = winning_trades / total_trades
            
            profits = [t.return_pct for t in trades if t.return_pct > 0]
            losses = [abs(t.return_pct) for t in trades if t.return_pct <= 0]
            
            avg_profit = np.mean(profits) if profits else 0
            avg_loss = np.mean(losses) if losses else 0
            profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 99.9
            
            avg_holding_days = np.mean([t.holding_days for t in trades])
        else:
            winning_trades = 0
            losing_trades = 0
            win_rate = 0
            profit_loss_ratio = 0
            avg_holding_days = 0
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'win_rate': win_rate,
            'profit_loss_ratio': profit_loss_ratio,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_holding_days': avg_holding_days,
        }
    
    def optimize_parameters(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
        ml_probs: Optional[pd.Series] = None,
        momentum_range: Optional[List[int]] = None,
        ma_range: Optional[List[int]] = None,
        metric: str = "sharpe_ratio",
        verbose: bool = True,
    ) -> Tuple[Tuple[int, int], BacktestResult, pd.DataFrame]:
        """
        参数网格搜索优化
        
        Parameters:
        -----------
        df300 : pd.DataFrame
            沪深300数据
        df1000 : pd.DataFrame
            中证1000数据
        ml_probs : pd.Series, optional
            ML风险概率
        momentum_range : List[int], optional
            动量参数范围
        ma_range : List[int], optional
            均线参数范围
        metric : str
            优化目标指标
        verbose : bool
            是否打印进度
            
        Returns:
        --------
        Tuple[Tuple[int, int], BacktestResult, pd.DataFrame]
            (最优参数, 最优结果, 所有结果表格)
        """
        if momentum_range is None:
            momentum_range = self.config.strategy.mom_range_list
        if ma_range is None:
            ma_range = self.config.strategy.ma_range_list
        
        # 计算基准收益（用于筛选）
        warmup_static = 30
        bench_ret = df300['close'].iloc[-1] / df300['close'].iloc[warmup_static] - 1
        max_dd_limit = self.config.trading.max_drawdown_limit
        
        if verbose:
            print("\n>>> 参数敏感性分析")
            print("=" * 100)
            header = f"{'动量':<6} | {'均线':<6} | {'累计收益':<12} | {'最大回撤':<12} | {'夏普比':<8} | {'胜率':<8} | {'盈亏比':<8} | {'状态'}"
            print(header)
            print("-" * 100)
        
        results = []
        best_score = -999
        best_params = (20, 12)
        best_result = None
        
        for mom in momentum_range:
            for ma in ma_range:
                result = self.run_backtest(
                    df300, df1000, mom, ma,
                    ml_probs=None,  # 参数优化阶段不使用ML
                    strategy_name=f"DMR(m={mom},ma={ma})"
                )
                
                # 筛选条件
                is_pass = (result.total_return > bench_ret) and (result.max_drawdown > max_dd_limit)
                status = "通过" if is_pass else "-"
                
                if verbose:
                    print(f"{mom:<6} | {ma:<6} | {result.total_return:>11.2%} | {result.max_drawdown:>11.2%} | "
                          f"{result.sharpe_ratio:>7.2f} | {result.win_rate:>7.1%} | {result.profit_loss_ratio:>7.2f} | {status}")
                
                # 记录结果
                results.append({
                    'momentum': mom,
                    'ma': ma,
                    'total_return': result.total_return,
                    'annual_return': result.annual_return,
                    'max_drawdown': result.max_drawdown,
                    'sharpe_ratio': result.sharpe_ratio,
                    'win_rate': result.win_rate,
                    'profit_loss_ratio': result.profit_loss_ratio,
                    'is_pass': is_pass,
                })
                
                # 更新最优
                score = getattr(result, metric)
                if is_pass and score > best_score:
                    best_score = score
                    best_params = (mom, ma)
                    best_result = result
        
        results_df = pd.DataFrame(results)
        
        if verbose:
            print("-" * 100)
            print(f"最优参数: MOM={best_params[0]}, MA={best_params[1]}")
            if best_result:
                print(f"最优指标: 夏普比率 {best_result.sharpe_ratio:.2f} | "
                      f"累计收益 {best_result.total_return:.2%} | "
                      f"年化收益 {best_result.annual_return:.2%} | "
                      f"最大回撤 {best_result.max_drawdown:.2%}")
            print("=" * 100)
        
        return best_params, best_result, results_df
    
    def compare_strategies(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
        momentum_window: int,
        ma_window: int,
        ml_probs: pd.Series,
    ) -> Dict[str, BacktestResult]:
        """
        策略对比
        
        Returns:
        --------
        Dict[str, BacktestResult]
            各策略回测结果
        """
        results = {}
        
        # DMR 策略
        results['DMR'] = self.run_backtest(
            df300, df1000, momentum_window, ma_window,
            ml_probs=None,
            strategy_name="DMR"
        )
        
        # DMR-ML 策略
        results['DMR-ML'] = self.run_backtest(
            df300, df1000, momentum_window, ma_window,
            ml_probs=ml_probs,
            strategy_name="DMR-ML"
        )
        
        # 基准（沪深300）
        common_idx = df300.index.intersection(df1000.index)
        bench = df300['close'].loc[common_idx]
        bench = bench / bench.iloc[0]
        bench_curve = pd.Series(bench.values, index=common_idx)
        
        bench_metrics = self._calculate_metrics(bench_curve, [])
        results['沪深300'] = BacktestResult(
            equity_curve=bench_curve,
            trades=[],
            strategy_name="沪深300",
            momentum_window=0,
            ma_window=0,
            **bench_metrics
        )
        
        return results


class ParameterSensitivityAnalyzer:
    """
    参数敏感性分析器
    用于分析参数变化对策略表现的影响
    """
    
    def __init__(self, engine: BacktestEngine):
        self.engine = engine
        
    def analyze(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
        base_momentum: int,
        base_ma: int,
        momentum_delta: int = 5,
        ma_delta: int = 2,
    ) -> Dict[str, pd.DataFrame]:
        """
        分析参数敏感性
        
        Returns:
        --------
        Dict[str, pd.DataFrame]
            各维度敏感性分析结果
        """
        config = get_config()
        
        # 动量敏感性
        mom_results = []
        for mom in range(base_momentum - momentum_delta * 2, base_momentum + momentum_delta * 2 + 1, momentum_delta):
            if mom > 0:
                result = self.engine.run_backtest(df300, df1000, mom, base_ma)
                mom_results.append({
                    'momentum': mom,
                    'sharpe': result.sharpe_ratio,
                    'return': result.total_return,
                    'drawdown': result.max_drawdown,
                })
        
        # 均线敏感性
        ma_results = []
        for ma in range(base_ma - ma_delta * 2, base_ma + ma_delta * 2 + 1, ma_delta):
            if ma > 0:
                result = self.engine.run_backtest(df300, df1000, base_momentum, ma)
                ma_results.append({
                    'ma': ma,
                    'sharpe': result.sharpe_ratio,
                    'return': result.total_return,
                    'drawdown': result.max_drawdown,
                })
        
        return {
            'momentum_sensitivity': pd.DataFrame(mom_results),
            'ma_sensitivity': pd.DataFrame(ma_results),
        }
