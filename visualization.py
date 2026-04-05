"""
DMR-ML - 可视化模块
使用 Plotly 创建交互式图表

Author: Kai
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import List, Dict, Optional, Any

from config import get_config
from backtest_engine import BacktestResult, Trade


class ChartTheme:
    """图表主题配置"""

    # 主题色板 - 暖色调
    PRIMARY = "#A0403C"       # 深红色（主策略）
    SECONDARY = "#3D5A80"     # 深蓝色（对比策略）
    NEUTRAL = "#B8B2A8"       # 暖灰色（基准）
    SUCCESS = "#5A8A6A"       # 柔和绿色
    WARNING = "#C49A4B"       # 暖金色
    DANGER = "#B85450"        # 柔和红色

    # 背景色 - 暖色浅色主题
    BG_COLOR = "#FAFAF7"      # 暖白色背景
    PAPER_COLOR = "#FAFAF7"   # 画布背景
    GRID_COLOR = "#E8E4DE"    # 暖浅灰网格线
    TEXT_COLOR = "#2D2A26"    # 深棕色文字

    # 字体
    FONT_FAMILY = "Georgia, 'Times New Roman', serif"

    @classmethod
    def get_layout(cls, title: str = "", height: int = 600) -> dict:
        """获取标准布局配置"""
        return dict(
            title=dict(
                text=title,
                font=dict(size=18, color=cls.TEXT_COLOR, family=cls.FONT_FAMILY),
                x=0.02,
                xanchor='left',
            ),
            font=dict(family=cls.FONT_FAMILY, color=cls.TEXT_COLOR),
            paper_bgcolor=cls.PAPER_COLOR,
            plot_bgcolor=cls.BG_COLOR,
            height=height,
            margin=dict(l=60, r=40, t=60, b=50),
            legend=dict(
                bgcolor='rgba(250,250,247,0.95)',
                bordercolor='#D4CFC7',
                borderwidth=1,
                font=dict(size=12, color=cls.TEXT_COLOR),
            ),
            xaxis=dict(
                gridcolor=cls.GRID_COLOR,
                gridwidth=1,
                showgrid=True,
                zeroline=False,
                tickfont=dict(color=cls.TEXT_COLOR),
                title_font=dict(color=cls.TEXT_COLOR),
            ),
            yaxis=dict(
                gridcolor=cls.GRID_COLOR,
                gridwidth=1,
                showgrid=True,
                zeroline=False,
                tickfont=dict(color=cls.TEXT_COLOR),
                title_font=dict(color=cls.TEXT_COLOR),
            ),
            hovermode='x unified',
        )


class EquityCurveChart:
    """净值曲线图"""
    
    def __init__(self, theme: ChartTheme = ChartTheme):
        self.theme = theme
    
    def create(
        self,
        curves: Dict[str, pd.Series],
        title: str = "策略净值走势对比",
        log_scale: bool = True,
    ) -> go.Figure:
        """
        创建净值曲线图
        
        Parameters:
        -----------
        curves : Dict[str, pd.Series]
            净值曲线字典 {名称: 净值序列}
        title : str
            图表标题
        log_scale : bool
            是否使用对数坐标
        """
        fig = go.Figure()
        
        # 颜色映射
        colors = {
            'DMR-ML': self.theme.PRIMARY,
            'DMR': self.theme.SECONDARY,
            '沪深300': self.theme.NEUTRAL,
        }
        
        # 线宽映射
        widths = {
            'DMR-ML': 3,
            'DMR': 2.5,
            '沪深300': 2,
        }
        
        for name, curve in curves.items():
            color = colors.get(name, self.theme.SECONDARY)
            width = widths.get(name, 2)
            
            # 计算收益率
            ret = (curve.iloc[-1] / curve.iloc[0] - 1) * 100
            
            fig.add_trace(go.Scatter(
                x=curve.index,
                y=curve.values,
                mode='lines',
                name=f'{name} ({ret:+.1f}%)',
                line=dict(color=color, width=width),
                hovertemplate=(
                    f'<b>{name}</b><br>' +
                    '日期: %{x|%Y-%m-%d}<br>' +
                    '净值: %{y:.4f}<br>' +
                    '<extra></extra>'
                ),
            ))
            
            # 添加终点标注
            fig.add_trace(go.Scatter(
                x=[curve.index[-1]],
                y=[curve.iloc[-1]],
                mode='markers+text',
                marker=dict(size=10, color=color, line=dict(color='white', width=2)),
                text=[f'+{ret:.1f}%'],
                textposition='top right',
                textfont=dict(color=color, size=11, family=self.theme.FONT_FAMILY),
                showlegend=False,
                hoverinfo='skip',
            ))
        
        # 布局
        layout = self.theme.get_layout(title)
        if log_scale:
            layout['yaxis']['type'] = 'log'
            layout['yaxis']['tickformat'] = '.0%'
            layout['yaxis']['tickvals'] = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
            layout['yaxis']['ticktext'] = ['0%', '+25%', '+50%', '+75%', '+100%', '+150%', '+200%']
        
        layout['xaxis']['title'] = '时间'
        layout['yaxis']['title'] = '累计收益率'
        layout['legend']['yanchor'] = 'top'
        layout['legend']['y'] = 0.99
        layout['legend']['xanchor'] = 'left'
        layout['legend']['x'] = 0.01
        
        fig.update_layout(**layout)
        
        return fig


class DrawdownChart:
    """回撤图"""
    
    def __init__(self, theme: ChartTheme = ChartTheme):
        self.theme = theme
    
    def create(
        self,
        curves: Dict[str, pd.Series],
        title: str = "策略回撤对比",
    ) -> go.Figure:
        """创建回撤对比图"""
        fig = go.Figure()
        
        colors = {
            'DMR-ML': self.theme.PRIMARY,
            'DMR': self.theme.SECONDARY,
            '沪深300': self.theme.NEUTRAL,
        }
        
        for name, curve in curves.items():
            # 计算回撤
            cummax = curve.cummax()
            dd = (curve - cummax) / cummax
            max_dd = dd.min()
            max_dd_date = dd.idxmin()
            
            color = colors.get(name, self.theme.SECONDARY)
            
            # 绘制填充区域
            fig.add_trace(go.Scatter(
                x=dd.index,
                y=dd.values,
                mode='lines',
                name=f'{name} ({max_dd:.2%})',
                line=dict(color=color, width=2),
                fill='tozeroy',
                fillcolor=f'rgba{tuple(list(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)) + [0.2])}',
                hovertemplate=(
                    f'<b>{name}</b><br>' +
                    '日期: %{x|%Y-%m-%d}<br>' +
                    '回撤: %{y:.2%}<br>' +
                    '<extra></extra>'
                ),
            ))
            
            # 标注最大回撤点
            fig.add_trace(go.Scatter(
                x=[max_dd_date],
                y=[max_dd],
                mode='markers+text',
                marker=dict(size=12, color=color, line=dict(color='white', width=2)),
                text=[f'{max_dd:.2%}'],
                textposition='bottom center',
                textfont=dict(color=color, size=10),
                showlegend=False,
                hoverinfo='skip',
            ))
        
        # 20%风控线
        fig.add_hline(
            y=-0.20,
            line=dict(color=self.theme.DANGER, width=2, dash='dash'),
            annotation_text='风控红线 -20%',
            annotation_position='bottom right',
            annotation_font_color=self.theme.DANGER,
        )
        
        layout = self.theme.get_layout(title)
        layout['yaxis']['tickformat'] = '.0%'
        layout['xaxis']['title'] = '时间'
        layout['yaxis']['title'] = '回撤幅度'
        
        fig.update_layout(**layout)
        
        return fig


class MonthlyHeatmap:
    """月度收益热力图"""
    
    def __init__(self, theme: ChartTheme = ChartTheme):
        self.theme = theme
    
    def create(
        self,
        equity_curve: pd.Series,
        title: str = "月度收益分布",
    ) -> go.Figure:
        """创建月度收益热力图"""
        
        # 计算月度收益
        monthly = equity_curve.resample('M').last().pct_change()
        df = monthly.to_frame(name='ret')
        df['Year'] = df.index.year
        df['Month'] = df.index.month
        pivot = df.pivot(index='Year', columns='Month', values='ret')
        
        # 计算YTD
        ytd = []
        for year in pivot.index:
            year_nav = equity_curve[str(year)]
            if len(year_nav) > 0:
                ytd.append(year_nav.iloc[-1] / year_nav.iloc[0] - 1)
            else:
                ytd.append(0)
        pivot[13] = ytd  # 13代表YTD
        
        # 月份标签
        month_labels = ['1月', '2月', '3月', '4月', '5月', '6月',
                       '7月', '8月', '9月', '10月', '11月', '12月', '全年']
        
        # 创建文字标注
        text_matrix = []
        for i in range(len(pivot.index)):
            row = []
            for j in range(len(pivot.columns)):
                val = pivot.iloc[i, j]
                if pd.notna(val):
                    row.append(f'{val:.1%}')
                else:
                    row.append('')
            text_matrix.append(row)
        
        # 颜色配置（红跌绿涨，A股风格，暖色调柔和版）
        colorscale = [
            [0, '#3D6B4F'],      # 深沉绿
            [0.35, '#5A8A6A'],   # 柔和绿
            [0.45, '#D5E1D8'],   # 极浅绿
            [0.5, '#FAFAF7'],    # 暖白
            [0.55, '#E8D0CC'],   # 极浅红
            [0.65, '#B85450'],   # 柔和红
            [1, '#A0403C'],      # 深红
        ]
        
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=month_labels,
            y=pivot.index.astype(str),
            text=text_matrix,
            texttemplate='%{text}',
            textfont=dict(size=11, color='black'),  # 统一黑色，在所有背景色上都清晰
            colorscale=colorscale,
            zmid=0,
            zmin=-0.15,
            zmax=0.15,
            colorbar=dict(
                title='月度收益',
                tickformat='.0%',
                tickfont=dict(color=self.theme.TEXT_COLOR),
                title_font=dict(color=self.theme.TEXT_COLOR),
            ),
            hovertemplate=(
                '年份: %{y}<br>' +
                '月份: %{x}<br>' +
                '收益: %{z:.2%}<br>' +
                '<extra></extra>'
            ),
        ))
        
        layout = self.theme.get_layout(title, height=600)
        layout['xaxis']['title'] = ''
        layout['yaxis']['title'] = '年份'
        layout['yaxis']['autorange'] = 'reversed'
        
        fig.update_layout(**layout)
        
        return fig


class ReturnDistributionChart:
    """收益分布图"""
    
    def __init__(self, theme: ChartTheme = ChartTheme):
        self.theme = theme
    
    def create(
        self,
        trades: List[Trade],
        title: str = "单笔交易收益分布",
    ) -> go.Figure:
        """创建收益分布图"""

        if not trades:
            fig = go.Figure()
            fig.add_annotation(
                text="无交易记录",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=20, color=self.theme.TEXT_COLOR),
            )
            return fig

        returns = pd.Series([t.return_pct for t in trades])

        # 统计
        mean_ret = returns.mean()
        median_ret = returns.median()
        profits = returns[returns > 0]
        losses = returns[returns <= 0]
        win_rate = len(profits) / len(returns)

        fig = go.Figure()

        # 统一分箱：先算好 bin edges，让盈亏柱子完美对齐
        bin_size = 0.02  # 2% 一档
        x_min = (returns.min() // bin_size) * bin_size - bin_size
        x_max = (returns.max() // bin_size + 1) * bin_size + bin_size

        # 亏损柱子 —— 柔和绿底 + 细描边
        fig.add_trace(go.Histogram(
            x=losses,
            name=f'亏损 ({len(losses)}笔)',
            marker=dict(
                color='rgba(90, 138, 106, 0.35)',
                line=dict(color='#5A8A6A', width=1),
            ),
            xbins=dict(start=x_min, end=0, size=bin_size),
            hovertemplate='收益区间: %{x}<br>笔数: %{y}<extra></extra>',
        ))

        # 盈利柱子 —— 柔和红底 + 细描边
        fig.add_trace(go.Histogram(
            x=profits,
            name=f'盈利 ({len(profits)}笔)',
            marker=dict(
                color='rgba(160, 64, 60, 0.35)',
                line=dict(color=self.theme.PRIMARY, width=1),
            ),
            xbins=dict(start=0, end=x_max, size=bin_size),
            hovertemplate='收益区间: %{x}<br>笔数: %{y}<extra></extra>',
        ))

        # 盈亏平衡线 —— 细而低调
        fig.add_vline(
            x=0,
            line=dict(color='#B8B2A8', width=1.5),
        )

        # 均值线
        fig.add_vline(
            x=mean_ret,
            line=dict(color=self.theme.WARNING, width=1.5, dash='dot'),
            annotation_text=f'均值 {mean_ret:.1%}',
            annotation_position='top right',
            annotation_font=dict(color=self.theme.WARNING, size=11,
                                 family=self.theme.FONT_FAMILY),
        )

        # 中位数线
        fig.add_vline(
            x=median_ret,
            line=dict(color='#B8B2A8', width=1, dash='dash'),
            annotation_text=f'中位数 {median_ret:.1%}',
            annotation_position='top left',
            annotation_font=dict(color='#8B8680', size=10,
                                 family=self.theme.FONT_FAMILY),
        )

        # 统计信息
        stats_text = (
            f'<b>交易统计</b><br>'
            f'总交易: {len(returns)} 笔<br>'
            f'胜率: {win_rate:.1%}<br>'
            f'平均收益: {mean_ret:.2%}<br>'
            f'中位数: {median_ret:.2%}'
        )

        fig.add_annotation(
            text=stats_text,
            xref="paper", yref="paper",
            x=0.98, y=0.98,
            xanchor='right', yanchor='top',
            showarrow=False,
            font=dict(size=11, color=self.theme.TEXT_COLOR,
                      family=self.theme.FONT_FAMILY),
            align='left',
            bgcolor='rgba(250,250,247,0.9)',
            bordercolor='#E8E4DE',
            borderwidth=1,
            borderpad=10,
        )

        layout = self.theme.get_layout(title)
        layout['barmode'] = 'relative'
        layout['bargap'] = 0.08
        layout['xaxis']['tickformat'] = '.0%'
        layout['xaxis']['title'] = '单笔收益率'
        layout['yaxis']['title'] = '交易笔数'
        layout['yaxis']['showgrid'] = False

        fig.update_layout(**layout)

        return fig


class RollingSharpeChart:
    """滚动夏普比率图"""
    
    def __init__(self, theme: ChartTheme = ChartTheme):
        self.theme = theme
    
    def create(
        self,
        curves: Dict[str, pd.Series],
        window: int = 126,
        title: str = "滚动夏普比率对比",
    ) -> go.Figure:
        """创建滚动夏普比率图"""
        
        config = get_config()
        rf = config.trading.risk_free_rate
        
        fig = go.Figure()
        
        colors = {
            'DMR-ML': self.theme.PRIMARY,
            'DMR': self.theme.SECONDARY,
        }
        
        for name, curve in curves.items():
            if name == '沪深300':
                continue
                
            daily_ret = curve.pct_change().dropna()
            rolling_mean = daily_ret.rolling(window).mean() * 252
            rolling_std = daily_ret.rolling(window).std() * np.sqrt(252)
            sharpe = (rolling_mean - rf) / rolling_std
            sharpe = sharpe.replace([np.inf, -np.inf], 0).fillna(0)
            
            avg_sharpe = sharpe[sharpe != 0].mean()
            color = colors.get(name, self.theme.SECONDARY)
            
            # 正夏普填充
            fig.add_trace(go.Scatter(
                x=sharpe.index,
                y=sharpe.clip(lower=0),
                mode='lines',
                line=dict(width=0),
                fill='tozeroy',
                fillcolor=f'rgba{tuple(list(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)) + [0.2])}',
                showlegend=False,
                hoverinfo='skip',
            ))
            
            # 负夏普填充
            fig.add_trace(go.Scatter(
                x=sharpe.index,
                y=sharpe.clip(upper=0),
                mode='lines',
                line=dict(width=0),
                fill='tozeroy',
                fillcolor='rgba(117,117,117,0.15)',
                showlegend=False,
                hoverinfo='skip',
            ))
            
            # 主线
            fig.add_trace(go.Scatter(
                x=sharpe.index,
                y=sharpe,
                mode='lines',
                name=f'{name} (均值: {avg_sharpe:.2f})',
                line=dict(color=color, width=2.5),
                hovertemplate=(
                    f'<b>{name}</b><br>' +
                    '日期: %{x|%Y-%m-%d}<br>' +
                    '夏普比率: %{y:.2f}<br>' +
                    '<extra></extra>'
                ),
            ))
        
        # 基准线
        fig.add_hline(y=0, line=dict(color=self.theme.TEXT_COLOR, width=1.5))
        fig.add_hline(
            y=0.3,
            line=dict(color=self.theme.WARNING, width=1.5, dash='dash'),
        )
        fig.add_hline(
            y=0.5,
            line=dict(color=self.theme.WARNING, width=1.5, dash='dash'),
            annotation_text='沪深300长期夏普约0.3-0.5，仅供参考',
            annotation_position='top left',
            annotation_font_color=self.theme.WARNING,
            annotation_font_size=10,
            annotation_bgcolor='rgba(250,250,247,0.95)',
            annotation_bordercolor=self.theme.WARNING,
            annotation_borderwidth=1,
            annotation_borderpad=4,
        )
        
        # 标题改为"半年滚动"更直观
        window_desc = "半年滚动" if window == 126 else f"{window}日"
        layout = self.theme.get_layout(f'{title} ({window_desc})')
        layout['xaxis']['title'] = '时间'
        layout['yaxis']['title'] = '夏普比率'
        layout['yaxis']['range'] = [-3.2, 4]
        
        fig.update_layout(**layout)
        
        return fig


class TradeSignalChart:
    """交易信号图"""
    
    def __init__(self, theme: ChartTheme = ChartTheme):
        self.theme = theme
    
    def create(
        self,
        df: pd.DataFrame,
        trades: List[Trade],
        target_asset: str = '1000',
        year: int = 2025,
        ma_window: int = 14,
        title: str = "",
    ) -> go.Figure:
        """创建交易信号图"""
        
        # 筛选数据
        start_dt = f"{year}-01-01"
        end_dt = f"{year}-12-31"
        mask = (df.index >= start_dt) & (df.index <= end_dt)
        
        if not mask.any():
            fig = go.Figure()
            fig.add_annotation(text=f"{year}年无数据", x=0.5, y=0.5, showarrow=False)
            return fig
        
        df_part = df.loc[mask]
        ma_line = df_part['close'].rolling(window=ma_window).mean()
        
        # 筛选交易记录
        # 筛选在该年度内活跃的交易（入场或出场在该年即显示）
        asset_trades = [t for t in trades if t.asset == target_asset and
                        (t.entry_date.year == year or t.exit_date.year == year)]
        
        asset_name = "沪深300" if target_asset == '300' else "中证1000"
        if not title:
            title = f"{year}年{asset_name}交易信号"
        
        fig = go.Figure()
        
        # 价格线
        fig.add_trace(go.Scatter(
            x=df_part.index,
            y=df_part['close'],
            mode='lines',
            name='收盘价',
            line=dict(color=self.theme.SECONDARY, width=2),
            hovertemplate='收盘价: %{y:,.0f}<extra></extra>',
        ))

        # 均线
        fig.add_trace(go.Scatter(
            x=df_part.index,
            y=ma_line,
            mode='lines',
            name=f'{ma_window}日均线',
            line=dict(color=self.theme.WARNING, width=2, dash='dash'),
            hovertemplate=f'{ma_window}日均线: %{{y:,.0f}}<extra></extra>',
        ))
        
        # 买入点
        buy_dates = [t.entry_date for t in asset_trades if t.entry_date in df_part.index]
        buy_prices = [df_part.loc[d, 'close'] for d in buy_dates]
        
        if buy_dates:
            fig.add_trace(go.Scatter(
                x=buy_dates,
                y=buy_prices,
                mode='markers',
                name='买入',
                marker=dict(
                    symbol='triangle-up',
                    size=15,
                    color=self.theme.PRIMARY,
                    line=dict(color='white', width=2),
                ),
                hovertemplate='买入: %{y:,.0f}<extra></extra>',
            ))
        
        # 卖出点 —— 合并为一个 trace
        sell_dates = []
        sell_prices = []
        sell_texts = []
        sell_textpos = []
        sell_textcolors = []
        for trade in asset_trades:
            if trade.exit_date in df_part.index:
                price = df_part.loc[trade.exit_date, 'close']
                ret = trade.return_pct
                sell_dates.append(trade.exit_date)
                sell_prices.append(price)
                sell_texts.append(f'{ret:+.1%}')
                sell_textpos.append('top center' if ret > 0 else 'bottom center')
                sell_textcolors.append(self.theme.PRIMARY if ret > 0 else self.theme.SUCCESS)

        if sell_dates:
            fig.add_trace(go.Scatter(
                x=sell_dates,
                y=sell_prices,
                mode='markers+text',
                name='卖出',
                marker=dict(
                    symbol='triangle-down',
                    size=15,
                    color=self.theme.SUCCESS,
                    line=dict(color='white', width=2),
                ),
                text=sell_texts,
                textposition=sell_textpos,
                textfont=dict(
                    color=sell_textcolors,
                    size=10,
                ),
                hovertemplate='卖出: %{y:,.0f}<extra></extra>',
            ))
        
        # 统计信息
        if asset_trades:
            total_trades = len(asset_trades)
            year_ret = sum(t.return_pct for t in asset_trades)
            win_trades = len([t for t in asset_trades if t.return_pct > 0])
            win_rate = win_trades / total_trades
            
            stats_text = (
                f'<b>{year}年交易统计</b><br>'
                f'交易次数: {total_trades} 笔<br>'
                f'胜率: {win_rate:.1%}<br>'
                f'累计收益: {year_ret:+.2%}'
            )
            
            fig.add_annotation(
                text=stats_text,
                xref="paper", yref="paper",
                x=0.02, y=0.98,  # 移到左上角，避免和价格曲线重合
                xanchor='left', yanchor='top',
                showarrow=False,
                font=dict(size=11, color=self.theme.TEXT_COLOR),
                align='left',
                bgcolor='rgba(250,250,247,0.95)',
                bordercolor='#D4CFC7',
                borderwidth=1,
                borderpad=8,
            )
        
        layout = self.theme.get_layout(title)
        layout['xaxis']['title'] = '时间'
        layout['yaxis']['title'] = '价格'
        
        fig.update_layout(**layout)
        
        return fig


class DashboardCharts:
    """
    仪表盘图表集合
    提供所有图表的统一接口
    """
    
    def __init__(self):
        self.theme = ChartTheme
        self.equity_chart = EquityCurveChart(self.theme)
        self.drawdown_chart = DrawdownChart(self.theme)
        self.monthly_heatmap = MonthlyHeatmap(self.theme)
        self.return_dist = ReturnDistributionChart(self.theme)
        self.rolling_sharpe = RollingSharpeChart(self.theme)
        self.signal_chart = TradeSignalChart(self.theme)
    
    def create_equity_curve(self, curves: Dict[str, pd.Series], **kwargs) -> go.Figure:
        """创建净值曲线图"""
        return self.equity_chart.create(curves, **kwargs)
    
    def create_drawdown(self, curves: Dict[str, pd.Series], **kwargs) -> go.Figure:
        """创建回撤图"""
        return self.drawdown_chart.create(curves, **kwargs)
    
    def create_monthly_heatmap(self, equity_curve: pd.Series, **kwargs) -> go.Figure:
        """创建月度热力图"""
        return self.monthly_heatmap.create(equity_curve, **kwargs)
    
    def create_return_distribution(self, trades: List[Trade], **kwargs) -> go.Figure:
        """创建收益分布图"""
        return self.return_dist.create(trades, **kwargs)
    
    def create_rolling_sharpe(self, curves: Dict[str, pd.Series], **kwargs) -> go.Figure:
        """创建滚动夏普比率图"""
        return self.rolling_sharpe.create(curves, **kwargs)
    
    def create_trade_signals(self, df: pd.DataFrame, trades: List[Trade], **kwargs) -> go.Figure:
        """创建交易信号图"""
        return self.signal_chart.create(df, trades, **kwargs)
