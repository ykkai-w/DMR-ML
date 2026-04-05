# -*- coding: utf-8 -*-
"""
DMR-ML 每日信号邮件发送脚本
由 cron 定时任务调用，为每位订阅者按其选择的策略模式生成并发送信号邮件。

用法：
    python send_daily_email.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

# 项目根目录
PROJECT_ROOT = str(Path(__file__).parent)
sys.path.insert(0, PROJECT_ROOT)

from data_service import DataService
from models import DMRStrategy, MLRiskModel, DMRMLStrategy
from reports import SignalGenerator
from subscription_service import SubscriptionManager, EmailSender, Subscriber

BEIJING_TZ = timezone(timedelta(hours=8))

# 模型预设参数
MODEL_PRESETS = {
    "adagio": {"momentum_window": 20, "ma_window": 14, "risk_trigger": 0.40, "risk_release": 0.33},
    "presto": {"momentum_window": 10, "ma_window": 14, "risk_trigger": 0.40, "risk_release": 0.33},
}


def compute_signal(model_id: str = "adagio") -> dict:
    """计算指定模型的今日信号"""
    preset = MODEL_PRESETS.get(model_id, MODEL_PRESETS["adagio"])
    mom = preset["momentum_window"]
    ma = preset["ma_window"]
    trig = preset["risk_trigger"]
    rel = preset["risk_release"]

    ds = DataService()
    df300, df1000 = ds.get_aligned_data()

    # ML 风险模型
    ml = MLRiskModel()
    ml_probs = ml.fit_predict(df300)

    # 生成信号
    gen = SignalGenerator(df300, df1000, ml_probs, mom, ma)
    raw = gen.generate_signal()

    # 映射为邮件模板所需的字段名
    ml_risk_raw = raw.get('ml_risk', {})
    ml_prob = ml_risk_raw.get('probability', 0) if isinstance(ml_risk_raw, dict) else float(ml_risk_raw)
    return {
        'date': raw.get('data_date', ''),
        'signal': raw.get('final_signal', '空仓'),
        'ml_risk': float(ml_prob),
        'reason': raw.get('final_reason', '-'),
    }


def main():
    now = datetime.now(BEIJING_TZ)
    print(f"[{now:%Y-%m-%d %H:%M}] 开始发送每日信号邮件...")

    manager = SubscriptionManager()
    sender = EmailSender()
    subscribers = manager.get_active_subscribers()

    if not subscribers:
        print("没有活跃订阅者，跳过。")
        return

    # 按模型分组，避免重复计算
    signal_cache = {}
    success_count = 0
    fail_count = 0

    for sub in subscribers:
        model_id = getattr(sub, 'model', 'adagio') or 'adagio'

        # 缓存每种模型的信号
        if model_id not in signal_cache:
            try:
                signal_cache[model_id] = compute_signal(model_id)
                print(f"  [{model_id}] 信号计算完成: {signal_cache[model_id].get('signal', '?')}")
            except Exception as e:
                print(f"  [{model_id}] 信号计算失败: {e}")
                signal_cache[model_id] = None

        signal_data = signal_cache[model_id]
        if signal_data is None:
            fail_count += 1
            continue

        model_name = "Adagio" if model_id == "adagio" else "Presto"
        signal_data_with_model = {**signal_data, 'model_name': model_name}
        ok, msg = sender.send_signal_email(sub.email, signal_data_with_model)
        if ok:
            success_count += 1
            print(f"  -> {sub.email} ({model_id}) 发送成功")
        else:
            fail_count += 1
            print(f"  -> {sub.email} ({model_id}) 发送失败: {msg}")

    print(f"完成。成功 {success_count}，失败 {fail_count}。")


if __name__ == "__main__":
    main()
