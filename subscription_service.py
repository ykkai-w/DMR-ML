# -*- coding: utf-8 -*-
"""
DMR-ML 订阅服务模块
处理邮箱订阅、存储和邮件发送功能

Author: Kai
Version: 1.0
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    """获取北京时间"""
    return datetime.now(BEIJING_TZ)

# 存储配置

# 订阅数据存储路径（本地JSON模式）
SUBSCRIPTION_FILE = os.path.join(os.path.dirname(__file__), 'subscribers.json')

def _get_storage_backend():
    """
    获取存储后端配置
    优先级：环境变量 > 默认(json)
    
    Returns:
        'supabase' 或 'json'
    """
    if os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_KEY'):
        return 'supabase'
    return 'json'

# 当前使用的存储后端
STORAGE_BACKEND = _get_storage_backend()

# 从环境变量获取邮箱授权码
def _get_email_password():
    """获取邮箱授权码"""
    return os.environ.get('EMAIL_PASSWORD', '')

# 邮件配置（使用SMTP，兼容多种邮件服务）
EMAIL_CONFIG = {
    'smtp_server': 'smtp.qq.com',  # QQ邮箱SMTP
    'smtp_port': 465,  # 使用SSL端口
    'sender_email': '2103318492@qq.com',  # 您的QQ邮箱
    'sender_password': _get_email_password(),  # QQ邮箱授权码
}


# 数据模型

@dataclass
class Subscriber:
    """订阅者数据模型"""
    email: str
    subscribe_time: str
    push_time: str = "08:00"
    model: str = "adagio"
    is_active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Subscriber':
        # 兼容数据库返回的多余字段（如 id / created_at）
        filtered = {
            'email': data.get('email', ''),
            'subscribe_time': data.get('subscribe_time', ''),
            'push_time': data.get('push_time', '08:00'),
            'model': data.get('model', 'adagio'),
            'is_active': data.get('is_active', True),
        }
        return cls(**filtered)


# Supabase 存储后端

class SupabaseManager:
    """Supabase 数据库管理器"""
    
    def __init__(self):
        self.client = None
        self.table_name = 'subscribers'
        self._connect()
    
    def _connect(self):
        """建立 Supabase 连接"""
        try:
            from supabase import create_client, Client
        except ImportError:
            raise ImportError("请安装 supabase: pip install supabase")
        
        # 获取配置
        url, key = self._get_credentials()
        if not url or not key:
            raise ValueError("未找到 Supabase 配置，请检查环境变量")
        
        self.client: Client = create_client(url, key)
        
        # 确保表存在（首次运行时创建）
        try:
            self.client.table(self.table_name).select("*").limit(1).execute()
        except Exception as e:
            print(f"Supabase 表可能不存在，需要手动创建: {e}")
    
    def _get_credentials(self) -> tuple:
        """从环境变量获取 Supabase 配置"""
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')
        return url, key
    
    def load_subscribers(self) -> List[Dict]:
        """从 Supabase 加载所有订阅者"""
        try:
            response = self.client.table(self.table_name).select("*").execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"从 Supabase 加载数据失败: {e}")
            return []
    
    def save_subscriber(self, subscriber: Dict):
        """添加新订阅者到 Supabase"""
        try:
            self.client.table(self.table_name).insert(subscriber).execute()
        except Exception as e:
            print(f"保存订阅者失败: {e}")
            raise
    
    def update_subscriber(self, email: str, data: Dict):
        """更新订阅者信息"""
        try:
            self.client.table(self.table_name).update(data).eq('email', email.lower()).execute()
        except Exception as e:
            print(f"更新订阅者失败: {e}")
    
    def delete_subscriber(self, email: str) -> bool:
        """从 Supabase 删除订阅者（软删除：设置 is_active=False）"""
        try:
            self.client.table(self.table_name).update({'is_active': False}).eq('email', email.lower()).execute()
            return True
        except Exception as e:
            print(f"删除订阅者失败: {e}")
            return False
    
    def find_subscriber(self, email: str) -> Optional[Dict]:
        """查找订阅者"""
        try:
            response = self.client.table(self.table_name).select("*").eq('email', email.lower()).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
        except Exception as e:
            print(f"查找订阅者失败: {e}")
        return None


# 订阅管理（统一接口）

class SubscriptionManager:
    """
    订阅管理器 - 统一接口
    根据配置自动选择存储后端（本地JSON或Supabase）
    """
    
    def __init__(self, file_path: str = SUBSCRIPTION_FILE, force_backend: str = None):
        """
        初始化订阅管理器
        
        Args:
            file_path: 本地JSON文件路径（仅json模式使用）
            force_backend: 强制使用的后端，'json' 或 'supabase'，不指定则自动检测
        """
        self.file_path = file_path
        self.backend = force_backend or STORAGE_BACKEND
        self.supabase_manager = None
        
        if self.backend == 'supabase':
            try:
                self.supabase_manager = SupabaseManager()
            except Exception as e:
                print(f"Supabase 连接失败，回退到本地JSON: {e}")
                self.backend = 'json'
        
        if self.backend == 'json':
            self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """确保订阅文件存在（仅JSON模式）"""
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
    
    def _load_subscribers(self) -> List[Dict]:
        """加载所有订阅者"""
        if self.backend == 'supabase' and self.supabase_manager:
            return self.supabase_manager.load_subscribers()
        else:
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
    
    def _save_subscribers(self, subscribers: List[Dict]):
        """保存订阅者列表（仅JSON模式使用）"""
        if self.backend == 'json':
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(subscribers, f, ensure_ascii=False, indent=2)
    
    def add_subscriber(self, email: str, push_time: str = "08:00", model: str = "adagio") -> tuple[bool, str]:
        """
        添加订阅者

        Returns:
            (成功标志, 消息)
        """
        # 验证邮箱格式
        if not self._validate_email(email):
            return False, "邮箱格式不正确，请检查后重试"

        email_lower = email.lower()

        if self.backend == 'supabase' and self.supabase_manager:
            # Supabase 模式
            existing = self.supabase_manager.find_subscriber(email_lower)
            if existing:
                if existing.get('is_active', True):
                    return False, "该邮箱已订阅，无需重复订阅"
                else:
                    # 重新激活
                    existing['is_active'] = True
                    existing['push_time'] = push_time
                    existing['model'] = model
                    self.supabase_manager.update_subscriber(email_lower, existing)
                    return True, "欢迎回来！已重新激活您的订阅"

            # 添加新订阅者
            new_subscriber = {
                'email': email_lower,
                'subscribe_time': get_beijing_now().strftime("%Y-%m-%d %H:%M:%S"),
                'push_time': push_time,
                'model': model,
                'is_active': True
            }
            self.supabase_manager.save_subscriber(new_subscriber)
            return True, "订阅成功，每日信号将准时送达"

        else:
            # JSON 模式
            subscribers = self._load_subscribers()

            # 检查是否已订阅
            for sub in subscribers:
                if sub['email'].lower() == email_lower:
                    if sub['is_active']:
                        return False, "该邮箱已订阅，无需重复订阅"
                    else:
                        # 重新激活
                        sub['is_active'] = True
                        sub['push_time'] = push_time
                        sub['model'] = model
                        self._save_subscribers(subscribers)
                        return True, "欢迎回来！已重新激活您的订阅"

            # 添加新订阅者
            new_subscriber = Subscriber(
                email=email_lower,
                subscribe_time=get_beijing_now().strftime("%Y-%m-%d %H:%M:%S"),
                push_time=push_time,
                model=model,
                is_active=True
            )
            subscribers.append(new_subscriber.to_dict())
            self._save_subscribers(subscribers)

            return True, "订阅成功，每日信号将准时送达"
    
    def remove_subscriber(self, email: str) -> tuple[bool, str]:
        """取消订阅"""
        email_lower = email.lower()
        
        if self.backend == 'supabase' and self.supabase_manager:
            if self.supabase_manager.delete_subscriber(email_lower):
                return True, "已取消订阅"
            return False, "未找到该邮箱的订阅记录"
        else:
            subscribers = self._load_subscribers()
            
            for sub in subscribers:
                if sub['email'].lower() == email_lower:
                    sub['is_active'] = False
                    self._save_subscribers(subscribers)
                    return True, "已取消订阅"
            
            return False, "未找到该邮箱的订阅记录"
    
    def get_active_subscribers(self) -> List[Subscriber]:
        """获取所有活跃订阅者"""
        subscribers = self._load_subscribers()
        return [Subscriber.from_dict(s) for s in subscribers if s.get('is_active', True)]
    
    def get_subscriber_count(self) -> int:
        """获取订阅者数量"""
        return len(self.get_active_subscribers())
    
    def get_storage_info(self) -> str:
        """获取当前存储后端信息（用于管理后台显示）"""
        if self.backend == 'supabase':
            return "Supabase 云数据库"
        else:
            return f"本地文件 ({self.file_path})"
    
    @staticmethod
    def _validate_email(email: str) -> bool:
        """验证邮箱格式"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))


# 邮件发送

class EmailSender:
    """邮件发送器"""
    
    def __init__(self, config: dict = None):
        self.config = config or EMAIL_CONFIG
    
    def send_signal_email(self, to_email: str, signal_data: dict) -> tuple[bool, str]:
        """
        发送每日信号邮件
        
        Args:
            to_email: 收件人邮箱
            signal_data: 信号数据，包含:
                - date: 日期
                - signal: 信号（沪深300/中证1000/空仓）
                - ml_risk: ML风险概率
                - reason: 信号原因
        """
        try:
            # 构建邮件内容
            model_name = signal_data.get('model_name', 'Adagio')
            subject = f"DMR-ML {model_name} · {signal_data['date']} 操作信号"
            
            html_content = self._build_email_html(signal_data)
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config['sender_email']
            msg['To'] = to_email
            
            # 添加HTML内容
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 发送邮件 - QQ邮箱使用SSL
            with smtplib.SMTP_SSL(self.config['smtp_server'], 465) as server:
                server.login(self.config['sender_email'], self.config['sender_password'])
                server.send_message(msg)
            
            return True, "邮件发送成功"
            
        except Exception as e:
            return False, f"邮件发送失败: {str(e)}"
    
    def send_welcome_email(self, to_email: str, push_time: str = "08:00", model_name: str = "Adagio") -> tuple[bool, str]:
        """
        发送订阅确认邮件
        """
        try:
            # 检查密码是否配置
            if not self.config['sender_password']:
                return False, "邮件配置错误：EMAIL_PASSWORD 未设置"

            subject = "DMR-ML · 订阅确认"
            html_content = self._build_welcome_email_html(push_time, model_name)
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config['sender_email']
            msg['To'] = to_email
            
            # 添加HTML内容
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 发送邮件
            with smtplib.SMTP_SSL(self.config['smtp_server'], 465, timeout=30) as server:
                server.login(self.config['sender_email'], self.config['sender_password'])
                server.send_message(msg)
            
            return True, "欢迎邮件发送成功"
            
        except smtplib.SMTPAuthenticationError:
            return False, "邮件发送失败：授权码错误或SMTP服务未开启"
        except smtplib.SMTPConnectError:
            return False, "邮件发送失败：无法连接邮件服务器（可能被网络限制）"
        except TimeoutError:
            return False, "邮件发送失败：连接超时（SMTP连接超时）"
        except Exception as e:
            return False, f"邮件发送失败: {type(e).__name__}: {str(e)}"
    
    def _build_email_html(self, signal_data: dict) -> str:
        """构建每日信号邮件HTML — 配合网站暖白+深蓝/深红配色"""

        signal = signal_data.get('signal', '空仓')
        if signal == '沪深300':
            signal_color = '#3D5A80'
            signal_desc = '大盘风格占优，建议配置沪深300指数基金或ETF'
        elif signal == '中证1000':
            signal_color = '#A0403C'
            signal_desc = '小盘风格占优，建议配置中证1000指数基金或ETF'
        else:
            signal_color = '#8B8680'
            signal_desc = 'ML风险门禁触发，建议空仓等待信号恢复'

        ml_risk = signal_data.get('ml_risk', 0)
        model_name = signal_data.get('model_name', 'Adagio')
        risk_status = '避险' if ml_risk > 0.40 else '正常'
        risk_bg = '#FFF5F5' if ml_risk > 0.40 else '#F0F7F4'
        risk_color = '#A0403C' if ml_risk > 0.40 else '#5A8A6A'

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#FAFAF7;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#FAFAF7" style="padding:24px 0;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" border="0" style="background:#FFFFFF;border:1px solid #E8E4DE;border-radius:4px;">

<!-- 头部 -->
<tr><td style="padding:32px 36px 24px;border-bottom:1px solid #E8E4DE;">
    <span style="font-family:Georgia,serif;font-size:22px;font-weight:700;color:#2D2A26;letter-spacing:-0.02em;">DMR-ML</span>
    <span style="font-size:13px;color:#A8A29E;margin-left:10px;">{signal_data.get('date', '')} 每日信号</span>
</td></tr>

<!-- 信号区域 -->
<tr><td style="padding:36px;text-align:center;">
    <div style="font-size:13px;color:#8B8680;letter-spacing:0.05em;text-transform:uppercase;">Today's Signal &middot; {model_name}</div>
    <div style="font-family:Georgia,serif;font-size:42px;font-weight:700;color:{signal_color};margin:12px 0 8px;letter-spacing:-0.01em;">{signal}</div>
    <div style="font-size:14px;color:#8B8680;line-height:1.6;">{signal_desc}</div>
</td></tr>

<!-- 数据明细 -->
<tr><td style="padding:0 36px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #E8E4DE;">
        <tr>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;color:#8B8680;">策略模式</td>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;font-weight:600;color:#2D2A26;text-align:right;">{model_name}</td>
        </tr>
        <tr>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;color:#8B8680;">ML 风险概率</td>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;font-weight:600;color:#2D2A26;text-align:right;">{ml_risk:.1%}</td>
        </tr>
        <tr>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;color:#8B8680;">风险状态</td>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;text-align:right;">
                <span style="display:inline-block;padding:3px 10px;border-radius:3px;font-size:12px;background:{risk_bg};color:{risk_color};">{risk_status}</span>
            </td>
        </tr>
        <tr>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;color:#8B8680;">信号依据</td>
            <td style="padding:14px 0;border-bottom:1px solid #F0EDE8;font-size:14px;color:#2D2A26;text-align:right;">{signal_data.get('reason', '-')}</td>
        </tr>
        <tr>
            <td style="padding:14px 0;font-size:14px;color:#8B8680;">执行时点</td>
            <td style="padding:14px 0;font-size:14px;color:#2D2A26;text-align:right;">当日开盘</td>
        </tr>
    </table>
</td></tr>

<!-- 页脚 -->
<tr><td style="padding:20px 36px;border-top:1px solid #E8E4DE;font-size:12px;color:#A8A29E;line-height:1.8;">
    <p style="margin:0;">风险提示：本策略基于历史数据回测，过往业绩不代表未来表现。投资有风险，决策需谨慎。</p>
    <p style="margin:8px 0 0;">DMR-ML 机器学习量化交易系统 &middot; &copy; 2026 ykkai-w</p>
    <p style="margin:4px 0 0;">如需取消订阅，请回复本邮件告知。</p>
</td></tr>

</table>
</td></tr>
</table>
</body></html>"""

        return html
    
    def _build_welcome_email_html(self, push_time: str = "08:00", model_name: str = "Adagio") -> str:
        """构建订阅确认邮件HTML — 配合网站暖白+深蓝/深红配色"""
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#FAFAF7;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#FAFAF7" style="padding:24px 0;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" border="0" style="background:#FFFFFF;border:1px solid #E8E4DE;border-radius:4px;">

<!-- 头部 -->
<tr><td style="padding:36px 36px 28px;border-bottom:1px solid #E8E4DE;">
    <div style="font-family:Georgia,serif;font-size:24px;font-weight:700;color:#2D2A26;letter-spacing:-0.02em;">DMR-ML</div>
    <div style="font-size:13px;color:#8B8680;margin-top:4px;">DMR-ML 机器学习量化交易系统</div>
</td></tr>

<!-- 正文 -->
<tr><td style="padding:32px 36px;">
    <p style="font-size:15px;color:#2D2A26;line-height:1.8;margin:0 0 16px;">您好，</p>
    <p style="font-size:15px;color:#2D2A26;line-height:1.8;margin:0 0 16px;">感谢订阅 DMR-ML 每日信号推送。您的订阅已生效。</p>

    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0;border:1px solid #E8E4DE;border-radius:4px;">
        <tr>
            <td style="padding:14px 20px;border-bottom:1px solid #F0EDE8;font-size:14px;color:#8B8680;">策略模式</td>
            <td style="padding:14px 20px;border-bottom:1px solid #F0EDE8;font-size:14px;font-weight:600;color:#2D2A26;text-align:right;">{model_name}</td>
        </tr>
        <tr>
            <td style="padding:14px 20px;border-bottom:1px solid #F0EDE8;font-size:14px;color:#8B8680;">推送时间</td>
            <td style="padding:14px 20px;border-bottom:1px solid #F0EDE8;font-size:14px;font-weight:600;color:#2D2A26;text-align:right;">每个交易日 {push_time}</td>
        </tr>
        <tr>
            <td style="padding:14px 20px;font-size:14px;color:#8B8680;">推送内容</td>
            <td style="padding:14px 20px;font-size:14px;color:#2D2A26;text-align:right;">操作信号 / ML风险概率 / 信号依据</td>
        </tr>
    </table>

    <p style="font-size:14px;color:#8B8680;line-height:1.8;margin:20px 0 0;">每日信号基于前一交易日收盘数据计算，包含持仓建议（沪深300 / 中证1000 / 空仓）及机器学习模型的风险评估。您可以据此参考配置对应的指数基金或ETF。</p>
</td></tr>

<!-- 访问按钮 -->
<tr><td style="padding:0 36px 32px;text-align:center;">
    <table cellpadding="0" cellspacing="0" border="0" align="center">
        <tr>
            <td style="border-radius:4px;background:#3D5A80;">
                <a href="https://dmrml.cn"
                   style="display:inline-block;padding:11px 28px;color:#ffffff;text-decoration:none;font-family:Georgia,serif;font-size:14px;font-weight:600;letter-spacing:0.02em;">
                    访问策略面板
                </a>
            </td>
        </tr>
    </table>
</td></tr>

<!-- 页脚 -->
<tr><td style="padding:20px 36px;border-top:1px solid #E8E4DE;font-size:12px;color:#A8A29E;line-height:1.8;">
    <p style="margin:0;">风险提示：策略基于历史回测，过往业绩不代表未来表现。投资有风险，决策需谨慎。</p>
    <p style="margin:8px 0 0;">DMR-ML &middot; &copy; 2026 ykkai-w</p>
    <p style="margin:4px 0 0;">如需取消订阅，请回复本邮件告知。</p>
</td></tr>

</table>
</td></tr>
</table>
</body></html>"""
        return html
    
    def send_batch_emails(self, subscribers: List[Subscriber], signal_data: dict) -> dict:
        """
        批量发送邮件
        
        Returns:
            {'success': 成功数, 'failed': 失败数, 'errors': 错误列表}
        """
        results = {'success': 0, 'failed': 0, 'errors': []}
        
        for sub in subscribers:
            success, msg = self.send_signal_email(sub.email, signal_data)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"{sub.email}: {msg}")
        
        return results


# 便捷函数

def subscribe_email(email: str, push_time: str = "08:00", model: str = "adagio") -> tuple[bool, str]:
    """订阅邮件服务"""
    manager = SubscriptionManager()
    return manager.add_subscriber(email, push_time, model)


def unsubscribe_email(email: str) -> tuple[bool, str]:
    """取消订阅"""
    manager = SubscriptionManager()
    return manager.remove_subscriber(email)


def get_subscriber_count() -> int:
    """获取订阅者数量"""
    manager = SubscriptionManager()
    return manager.get_subscriber_count()


def send_daily_signals(signal_data: dict) -> dict:
    """发送每日信号给所有订阅者"""
    manager = SubscriptionManager()
    sender = EmailSender()
    subscribers = manager.get_active_subscribers()
    return sender.send_batch_emails(subscribers, signal_data)


def load_subscribers() -> List[Subscriber]:
    """加载所有订阅者（用于管理员后台）"""
    manager = SubscriptionManager()
    return manager.get_active_subscribers()


def delete_subscriber(email: str) -> tuple[bool, str]:
    """删除订阅者（管理员功能）"""
    return unsubscribe_email(email)


# 示例运行

if __name__ == "__main__":
    # 示例
    success, msg = subscribe_email("test@example.com")
    print(f"订阅结果: {msg}")
    
    # 查看订阅者数量
    count = get_subscriber_count()
    print(f"当前订阅者数量: {count}")
