#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 配置文件 - 请根据实际情况修改
class Config:
    # 调试模式
    DEBUG = True
    
    # 警报冷却时间 (秒)
    ALERT_COOLDOWN = 300  # 5分钟
    
    # 是否启用Telegram通知
    TELEGRAM_ENABLED = True
    
    # Telegram配置 - 必须设置您的实际值
    TELEGRAM_BOT_TOKEN = "TOKEN"  # 替换为您的BOT_TOKEN
    TELEGRAM_CHAT_ID = "ID"  # 替换为您的Chat ID
    
    # 代理设置
    USE_PROXY = False
    PROXY_URL = "http://user:pass@host:port"  # 如果需要代理
    
    # 是否发送启动通知
    STARTUP_NOTIFICATION = True
    
    # 监控间隔 (秒)
    CHECK_INTERVAL = 60
    
    # API 端点
    SPOT_API_URL = "https://api.binance.com"
    FUTURES_API_URL = "https://fapi.binance.com"
    
    # 默认监控配置
    DEFAULT_SYMBOLS = ["BTCUSDT_PERP", "ETHUSDT_PERP","BNBUSDT_PERP","DOGEUSDT_PERP","SOLUSDT_PERP"]
    DEFAULT_TIME_WINDOWS = {5: 0.5, 15: 1.0, 60: 2.0}  # 时间窗口（分钟）和阈值（%）
    
    # 最大监控配置数
    MAX_MONITORING_CONFIGS = 20
    
    # 历史数据保留时长 (小时)
    MAX_HISTORY_HOURS = 24
    
    # 数据文件
    DATA_FILE = "price_history.json"
    
    # 状态文件
    STATE_FILE = "bot_state.json"
    
    @property
    def valid_chat_id(self):
        """验证并返回有效的 Chat ID"""
        chat_id = self.TELEGRAM_CHAT_ID
        
        # 如果是字符串形式的数字，转换为整数
        if isinstance(chat_id, str) and chat_id.strip().isdigit():
            return int(chat_id.strip())
        
        # 如果是整数，直接返回
        if isinstance(chat_id, int):
            return chat_id
        
        # 无效格式
        return None

# 创建配置实例
config = Config()

