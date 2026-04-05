"""
DMR-ML - 报表生成模块
生成策略分析报告

Author: Kai
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from config import get_config

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    """获取北京时间"""
    return datetime.now(BEIJING_TZ)
from backtest_engine import BacktestResult, Trade


class MetricsCalculator:
    """
    指标计算器
    计算各类风险调整收益指标
    """
    
    def __init__(self, equity_curve: pd.Series):
        self.equity_curve = equity_curve
        self.config = get_config()
        self.daily_returns = equity_curve.pct_change().dropna()
    
    def calculate_annual_return(self) -> float:
        """年化收益率"""
        total_ret = self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1
        days = (self.equity_curve.index[-1] - self.equity_curve.index[0]).days
        return (1 + total_ret) ** (365 / days) - 1 if days > 0 else 0
    
    def calculate_volatility(self) -> float:
        """年化波动率"""
        return self.daily_returns.std() * np.sqrt(252)
    
    def calculate_sharpe_ratio(self) -> float:
        """夏普比率"""
        rf = self.config.trading.risk_free_rate
        ann_ret = self.daily_returns.mean() * 252
        vol = self.calculate_volatility()
        return (ann_ret - rf) / vol if vol > 0 else 0
    
    def calculate_sortino_ratio(self) -> float:
        """索提诺比率"""
        rf = self.config.trading.risk_free_rate
        ann_ret = self.daily_returns.mean() * 252
        downside = self.daily_returns[self.daily_returns < 0]
        downside_std = downside.std() * np.sqrt(252) if len(downside) > 0 else 0
        return (ann_ret - rf) / downside_std if downside_std > 0 else 0
    
    def calculate_calmar_ratio(self) -> float:
        """卡玛比率（年化收益/最大回撤）"""
        ann_ret = self.calculate_annual_return()
        max_dd = self.calculate_max_drawdown()
        return ann_ret / abs(max_dd) if max_dd != 0 else 0
    
    def calculate_max_drawdown(self) -> float:
        """最大回撤"""
        cummax = self.equity_curve.cummax()
        drawdown = (self.equity_curve - cummax) / cummax
        return drawdown.min()
    
    def calculate_drawdown_series(self) -> pd.Series:
        """回撤序列"""
        cummax = self.equity_curve.cummax()
        return (self.equity_curve - cummax) / cummax
    
    def calculate_rolling_sharpe(self, window: int = 126) -> pd.Series:
        """滚动夏普比率"""
        rf = self.config.trading.risk_free_rate
        rolling_mean = self.daily_returns.rolling(window).mean() * 252
        rolling_std = self.daily_returns.rolling(window).std() * np.sqrt(252)
        sharpe = (rolling_mean - rf) / rolling_std
        return sharpe.replace([np.inf, -np.inf], 0).fillna(0)
    
    def calculate_monthly_returns(self) -> pd.DataFrame:
        """月度收益矩阵"""
        monthly = self.equity_curve.resample('M').last().pct_change()
        df = monthly.to_frame(name='ret')
        df['Year'] = df.index.year
        df['Month'] = df.index.month
        pivot = df.pivot(index='Year', columns='Month', values='ret')
        
        # 添加年度收益
        ytd = []
        for year in pivot.index:
            year_nav = self.equity_curve[str(year)]
            if len(year_nav) > 0:
                ytd.append(year_nav.iloc[-1] / year_nav.iloc[0] - 1)
            else:
                ytd.append(0)
        pivot['YTD'] = ytd
        
        return pivot
    
    def calculate_all_metrics(self) -> Dict[str, float]:
        """计算所有指标"""
        return {
            'total_return': self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1,
            'annual_return': self.calculate_annual_return(),
            'volatility': self.calculate_volatility(),
            'max_drawdown': self.calculate_max_drawdown(),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'sortino_ratio': self.calculate_sortino_ratio(),
            'calmar_ratio': self.calculate_calmar_ratio(),
        }


class TradeAnalyzer:
    """
    交易分析器
    分析交易记录，生成交易统计
    """
    
    def __init__(self, trades: List[Trade]):
        self.trades = trades
        self.df = pd.DataFrame([{
            'asset': t.asset,
            'entry_date': t.entry_date,
            'exit_date': t.exit_date,
            'return': t.return_pct,
            'days': t.holding_days,
            'exit_reason': t.exit_reason,
        } for t in trades]) if trades else pd.DataFrame()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取交易统计摘要"""
        if self.df.empty:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'profit_loss_ratio': 0,
                'avg_holding_days': 0,
                'avg_return': 0,
            }
        
        wins = self.df[self.df['return'] > 0]
        losses = self.df[self.df['return'] <= 0]
        
        avg_win = wins['return'].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses['return'].mean()) if len(losses) > 0 else 0
        
        return {
            'total_trades': len(self.df),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': len(wins) / len(self.df) if len(self.df) > 0 else 0,
            'profit_loss_ratio': avg_win / avg_loss if avg_loss > 0 else 99.9,
            'avg_holding_days': self.df['days'].mean(),
            'avg_return': self.df['return'].mean(),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': self.df['return'].max() if len(self.df) > 0 else 0,
            'worst_trade': self.df['return'].min() if len(self.df) > 0 else 0,
        }
    
    def get_yearly_allocation(self) -> pd.DataFrame:
        """年度资产配置统计"""
        if self.df.empty:
            return pd.DataFrame()
        
        self.df['year'] = self.df['exit_date'].apply(lambda x: x.year)
        yearly_stats = []
        
        for year in sorted(self.df['year'].unique()):
            sub = self.df[self.df['year'] == year]
            d300 = sub[sub['asset'] == '300']['days'].sum()
            d1000 = sub[sub['asset'] == '1000']['days'].sum()
            d_cash = max(0, 365 - d300 - d1000)
            
            # 风格判断
            if d_cash > 200:
                style = "低仓位"
            elif d300 > d1000 * 1.5:
                style = "偏大盘"
            elif d1000 > d300 * 1.5:
                style = "偏小盘"
            else:
                style = "均衡"
            
            yearly_stats.append({
                '年份': year,
                '沪深300 (天)': d300,
                '中证1000 (天)': d1000,
                '空仓 (天)': d_cash,
                '市场风格': style,
            })
        
        return pd.DataFrame(yearly_stats)
    
    def get_top_trades(self, n: int = 5, ascending: bool = False) -> pd.DataFrame:
        """获取最优/最差交易"""
        if self.df.empty:
            return pd.DataFrame()
        
        return self.df.sort_values('return', ascending=ascending).head(n)
    
    def get_return_distribution(self) -> Dict[str, Any]:
        """收益分布统计"""
        if self.df.empty:
            return {}
        
        returns = self.df['return']
        return {
            'mean': returns.mean(),
            'median': returns.median(),
            'std': returns.std(),
            'skewness': returns.skew(),
            'kurtosis': returns.kurtosis(),
            'min': returns.min(),
            'max': returns.max(),
            'q25': returns.quantile(0.25),
            'q75': returns.quantile(0.75),
        }


class ReportGenerator:
    """
    报告生成器
    生成完整的策略分析报告
    """
    
    def __init__(self, result: BacktestResult, benchmark_result: Optional[BacktestResult] = None):
        self.result = result
        self.benchmark = benchmark_result
        self.config = get_config()
        
        self.metrics_calc = MetricsCalculator(result.equity_curve)
        self.trade_analyzer = TradeAnalyzer(result.trades)
    
    def generate_summary(self) -> Dict[str, Any]:
        """生成摘要报告"""
        metrics = self.metrics_calc.calculate_all_metrics()
        trade_stats = self.trade_analyzer.get_summary()
        
        summary = {
            'strategy_name': self.result.strategy_name,
            'period': {
                'start': self.result.start_date.strftime('%Y-%m-%d') if self.result.start_date else '',
                'end': self.result.end_date.strftime('%Y-%m-%d') if self.result.end_date else '',
                'days': (self.result.end_date - self.result.start_date).days if self.result.start_date and self.result.end_date else 0,
            },
            'parameters': {
                'momentum_window': self.result.momentum_window,
                'ma_window': self.result.ma_window,
            },
            'performance': metrics,
            'trading': trade_stats,
        }
        
        # 如果有基准，计算相对指标
        if self.benchmark:
            bench_metrics = MetricsCalculator(self.benchmark.equity_curve).calculate_all_metrics()
            summary['relative'] = {
                'excess_return': metrics['total_return'] - bench_metrics['total_return'],
                'excess_annual_return': metrics['annual_return'] - bench_metrics['annual_return'],
                'drawdown_improvement': bench_metrics['max_drawdown'] - metrics['max_drawdown'],
                'sharpe_improvement': metrics['sharpe_ratio'] - bench_metrics['sharpe_ratio'],
            }
        
        return summary
    
    def generate_monthly_report(self) -> pd.DataFrame:
        """生成月度收益报告"""
        return self.metrics_calc.calculate_monthly_returns()
    
    def generate_trade_report(self) -> Dict[str, Any]:
        """生成交易报告"""
        return {
            'summary': self.trade_analyzer.get_summary(),
            'yearly_allocation': self.trade_analyzer.get_yearly_allocation().to_dict('records'),
            'top_winners': self.trade_analyzer.get_top_trades(5, ascending=False).to_dict('records'),
            'top_losers': self.trade_analyzer.get_top_trades(5, ascending=True).to_dict('records'),
            'distribution': self.trade_analyzer.get_return_distribution(),
        }
    
    def print_summary(self):
        """打印策略摘要"""
        summary = self.generate_summary()
        
        print("\n" + "=" * 70)
        print(f"策略绩效报告: {summary['strategy_name']}")
        print("-" * 70)
        print(f"回测区间: {summary['period']['start']} 至 {summary['period']['end']}")
        print(f"参数设置: 动量窗口={summary['parameters']['momentum_window']}, 均线窗口={summary['parameters']['ma_window']}")
        print("-" * 70)
        
        perf = summary['performance']
        print(f"{'累计收益':<15}: {perf['total_return']:.2%}")
        print(f"{'年化收益':<15}: {perf['annual_return']:.2%}")
        print(f"{'年化波动率':<15}: {perf['volatility']:.2%}")
        print(f"{'最大回撤':<15}: {perf['max_drawdown']:.2%}")
        print(f"{'夏普比率':<15}: {perf['sharpe_ratio']:.2f}")
        print(f"{'索提诺比率':<15}: {perf['sortino_ratio']:.2f}")
        print(f"{'卡玛比率':<15}: {perf['calmar_ratio']:.2f}")
        
        print("-" * 70)
        trade = summary['trading']
        print(f"{'总交易次数':<15}: {trade['total_trades']}")
        print(f"{'胜率':<15}: {trade['win_rate']:.1%}")
        print(f"{'盈亏比':<15}: {trade['profit_loss_ratio']:.2f}")
        print(f"{'平均持仓天数':<15}: {trade['avg_holding_days']:.1f}")
        
        if 'relative' in summary:
            print("-" * 70)
            rel = summary['relative']
            print("相对基准:")
            print(f"{'超额收益':<15}: {rel['excess_return']:+.2%}")
            print(f"{'超额年化':<15}: {rel['excess_annual_return']:+.2%}")
            print(f"{'回撤改善':<15}: {rel['drawdown_improvement']:+.2%}")
            print(f"{'夏普提升':<15}: {rel['sharpe_improvement']:+.2f}")
        
        print("=" * 70)


class SignalGenerator:
    """
    实时信号生成器
    生成当日交易建议
    """
    
    def __init__(
        self,
        df300: pd.DataFrame,
        df1000: pd.DataFrame,
        ml_probs: pd.Series,
        momentum_window: int,
        ma_window: int,
    ):
        self.df300 = df300
        self.df1000 = df1000
        self.ml_probs = ml_probs
        self.momentum_window = momentum_window
        self.ma_window = ma_window
        self.config = get_config()
    
    def generate_signal(self) -> Dict[str, Any]:
        """生成当日信号"""
        last_idx = -1
        
        # 价格数据
        p300 = self.df300['close'].iloc[last_idx]
        p1000 = self.df1000['close'].iloc[last_idx]
        
        # 动量
        mom300 = p300 / self.df300['close'].iloc[last_idx - self.momentum_window - 1] - 1
        mom1000 = p1000 / self.df1000['close'].iloc[last_idx - self.momentum_window - 1] - 1
        
        # 均线
        ma300 = self.df300['close'].iloc[-self.ma_window:].mean()
        ma1000 = self.df1000['close'].iloc[-self.ma_window:].mean()
        
        # 偏离度
        bias300 = (p300 - ma300) / ma300
        bias1000 = (p1000 - ma1000) / ma1000
        
        # DMR信号
        sig300 = (p300 > ma300) and (mom300 > 0)
        sig1000 = (p1000 > ma1000) and (mom1000 > 0)
        
        if sig300 and sig1000:
            if mom300 > mom1000:
                dmr_signal = "沪深300"
                dmr_reason = "两指数均多头，大盘更强"
            else:
                dmr_signal = "中证1000"
                dmr_reason = "两指数均多头，小盘更强"
        elif sig300:
            dmr_signal = "沪深300"
            dmr_reason = "大盘多头，小盘走弱"
        elif sig1000:
            dmr_signal = "中证1000"
            dmr_reason = "小盘多头，大盘走弱"
        else:
            dmr_signal = "空仓"
            dmr_reason = "无有效信号"
        
        # ML风险评估
        ml_prob = self.ml_probs.iloc[last_idx]
        ml_trigger = self.config.ml.risk_trigger_threshold
        ml_release = self.config.ml.risk_release_threshold
        ml_alert = ml_prob > ml_trigger
        
        # 最终信号
        if ml_alert:
            final_signal = "空仓"
            final_reason = f"ML风险概率 {ml_prob:.1%} 超过阈值，触发避险"
        else:
            final_signal = dmr_signal
            final_reason = dmr_reason
        
        return {
            'data_date': self.df300.index[last_idx].strftime('%Y-%m-%d'),
            'indicators': {
                'csi300': {
                    'price': p300,
                    'momentum': mom300,
                    'ma': ma300,
                    'bias': bias300,
                    'signal': sig300,
                },
                'csi1000': {
                    'price': p1000,
                    'momentum': mom1000,
                    'ma': ma1000,
                    'bias': bias1000,
                    'signal': sig1000,
                },
            },
            'ml_risk': {
                'probability': ml_prob,
                'trigger_threshold': ml_trigger,
                'release_threshold': ml_release,
                'is_alert': ml_alert,
            },
            'dmr_signal': dmr_signal,
            'dmr_reason': dmr_reason,
            'final_signal': final_signal,
            'final_reason': final_reason,
            'execution_time': '当日开盘',
        }
    
    def print_signal(self):
        """打印信号报告"""
        signal = self.generate_signal()
        now = get_beijing_now()  # 使用北京时间
        
        weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
        is_weekend = now.weekday() >= 5
        is_trading_hours = 9 <= now.hour < 15
        
        if is_weekend:
            status = "休市（周末）"
        elif is_trading_hours:
            status = "交易时段"
        else:
            status = "非交易时段"
        
        print("\n" + "=" * 80)
        print("当日策略信号")
        print("-" * 80)
        print(f"系统状态: {status}")
        print(f"系统时间: {now.strftime('%Y-%m-%d %H:%M')} ({weekday_map[now.weekday()]})")
        print(f"数据日期: {signal['data_date']}")
        print("-" * 40)
        
        print("技术指标:")
        ind = signal['indicators']
        print(f"  沪深300:  动量 {ind['csi300']['momentum']:>7.2%} | 现价 {ind['csi300']['price']:>7.0f} | "
              f"均线 {ind['csi300']['ma']:>7.0f} | 偏离 {ind['csi300']['bias']:>6.2%}")
        print(f"  中证1000: 动量 {ind['csi1000']['momentum']:>7.2%} | 现价 {ind['csi1000']['price']:>7.0f} | "
              f"均线 {ind['csi1000']['ma']:>7.0f} | 偏离 {ind['csi1000']['bias']:>6.2%}")
        
        print("-" * 40)
        print("ML风险评估:")
        ml = signal['ml_risk']
        print(f"  风险概率: {ml['probability']:.2%}")
        print(f"  阈值: {ml['trigger_threshold']:.0%} (触发) / {ml['release_threshold']:.0%} (解除)")
        print(f"  状态: {'避险模式' if ml['is_alert'] else '正常'}")
        
        print("-" * 40)
        print(f"DMR策略信号: {signal['dmr_signal']}")
        print("-" * 40)
        print(f">>> DMR-ML策略信号: {signal['final_signal']} <<<")
        print("-" * 40)
        print(f"执行时点: {signal['execution_time']}")
        print(f"决策依据: {signal['final_reason']}")
        print("=" * 80)
        
        return signal
