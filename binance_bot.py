#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import logging
import requests
import threading
import re
from datetime import datetime, timedelta
from config import Config

# 设置日志
logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('binance_monitor.log')
    ]
)
logger = logging.getLogger('BinanceMonitor')

class BotState:
    """机器人状态管理（支持多币种多时间段多阈值）"""
    def __init__(self, config):
        self.config = config
        self.state_file = "bot_state.json"
        
        # 初始化状态
        self.state = {
            "monitoring_enabled": True,
            "monitoring_configs": [],
            "last_update": datetime.utcnow().isoformat()
        }
        
        # 初始化默认配置
        for symbol in config.DEFAULT_SYMBOLS:
            for window, threshold in config.DEFAULT_TIME_WINDOWS.items():
                self.state["monitoring_configs"].append({
                    "symbol": symbol,
                    "market_type": "spot",  # 默认现货
                    "window": window,
                    "threshold": threshold
                })
        
        self.load_state()
        # 确保所有配置的window都是整数
        self.convert_window_to_int()
    
    def load_state(self):
        """从文件加载状态"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    loaded_state = json.load(f)
                    
                    # 迁移旧版本状态
                    if "symbols" in loaded_state:
                        logger.info("检测到旧版状态，进行迁移...")
                        self.migrate_old_state(loaded_state)
                    else:
                        self.state = loaded_state
                    
                    logger.info("加载机器人状态成功")
            except Exception as e:
                logger.error(f"加载状态失败: {e}")
                # 出错时保存当前状态
                self.save_state()
    
    def convert_window_to_int(self):
        """确保所有 window 值都是整数"""
        for config in self.state["monitoring_configs"]:
            if isinstance(config["window"], str):
                try:
                    config["window"] = int(config["window"])
                    logger.debug(f"转换 window 值为整数: {config['symbol']} {config['window']}")
                except ValueError:
                    logger.error(f"无法转换 window 值为整数: {config['symbol']} {config['window']}")
    
    def migrate_old_state(self, old_state):
        """迁移旧版本状态"""
        self.state["monitoring_enabled"] = old_state.get("monitoring_enabled", True)
        
        # 转换旧版币种列表和窗口配置
        symbols = old_state.get("symbols", [])
        time_windows = old_state.get("time_windows", {})
        
        self.state["monitoring_configs"] = []
        for symbol in symbols:
            # 自动检测市场类型
            market_type = "futures" if "_PERP" in symbol else "spot"
            clean_symbol = symbol.replace("_PERP", "")
            
            for window, threshold in time_windows.items():
                # 确保 window 是整数
                try:
                    window_int = int(window)
                except (TypeError, ValueError):
                    logger.warning(f"跳过无效的 window 值: {window}")
                    continue
                
                self.state["monitoring_configs"].append({
                    "symbol": clean_symbol,
                    "market_type": market_type,
                    "window": window_int,
                    "threshold": threshold
                })
        
        self.save_state()
        logger.info("旧版状态迁移完成")
    
    def save_state(self):
        """保存状态到文件"""
        try:
            self.state["last_update"] = datetime.utcnow().isoformat()
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")
    
    def is_monitoring_enabled(self):
        return self.state["monitoring_enabled"]
    
    def enable_monitoring(self):
        self.state["monitoring_enabled"] = True
        self.save_state()
    
    def disable_monitoring(self):
        self.state["monitoring_enabled"] = False
        self.save_state()
    
    def add_config(self, symbol, market_type, window, threshold):
        """添加新的监控配置"""
        # 确保 window 是整数
        if isinstance(window, str):
            try:
                window = int(window)
            except ValueError:
                logger.error(f"无效的 window 值: {window}")
                return False
        
        # 检查是否已存在相同配置
        for config in self.state["monitoring_configs"]:
            if (config["symbol"] == symbol and 
                config["market_type"] == market_type and 
                config["window"] == window):
                return False  # 已存在相同配置
        
        # 检查配置数量限制
        if len(self.state["monitoring_configs"]) >= self.config.MAX_MONITORING_CONFIGS:
            return None  # 达到最大配置数
        
        # 添加新配置
        self.state["monitoring_configs"].append({
            "symbol": symbol,
            "market_type": market_type,
            "window": window,
            "threshold": threshold
        })
        self.save_state()
        return True
    
    def remove_config(self, symbol, market_type, window=None):
        """移除监控配置"""
        # 如果指定了时间窗口，移除特定配置
        if window is not None:
            # 确保 window 是整数
            if isinstance(window, str):
                try:
                    window = int(window)
                except ValueError:
                    logger.error(f"无效的 window 值: {window}")
                    return False
            
            original_count = len(self.state["monitoring_configs"])
            self.state["monitoring_configs"] = [
                config for config in self.state["monitoring_configs"]
                if not (config["symbol"] == symbol and 
                        config["market_type"] == market_type and 
                        config["window"] == window)
            ]
            new_count = len(self.state["monitoring_configs"])
            self.save_state()
            return original_count != new_count
        
        # 移除该币种所有配置
        original_count = len(self.state["monitoring_configs"])
        self.state["monitoring_configs"] = [
            config for config in self.state["monitoring_configs"]
            if not (config["symbol"] == symbol and config["market_type"] == market_type)
        ]
        new_count = len(self.state["monitoring_configs"])
        self.save_state()
        return original_count != new_count
    
    def get_symbol_configs(self, symbol, market_type):
        """获取指定币种的所有配置"""
        return [
            config for config in self.state["monitoring_configs"]
            if config["symbol"] == symbol and config["market_type"] == market_type
        ]
    
    def get_all_configs(self):
        """获取所有监控配置"""
        return self.state["monitoring_configs"]
    
    def get_unique_symbols(self):
        """获取所有唯一币种（含市场类型）"""
        return list(set(
            (config["symbol"], config["market_type"]) 
            for config in self.state["monitoring_configs"]
        ))
    
    def get_formatted_symbol(self, symbol, market_type):
        """获取格式化后的交易对名称"""
        return f"{symbol}_PERP" if market_type == "futures" else symbol

class PriceHistory:
    """价格历史数据管理"""
    def __init__(self, data_file=Config.DATA_FILE, max_hours=Config.MAX_HISTORY_HOURS):
        self.data_file = data_file
        self.max_hours = max_hours
        self.history = self.load_history()
    
    def load_history(self):
        """从文件加载历史数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载历史数据失败: {e}")
                return {}
        return {}
    
    def save_history(self):
        """保存历史数据到文件"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            logger.error(f"保存历史数据失败: {e}")
    
    def add_price(self, symbol, market_type, price):
        """添加新的价格记录"""
        # 忽略无效价格
        if price is None or price <= 0:
            logger.warning(f"忽略无效价格: {symbol} {market_type} {price}")
            return
            
        # 使用组合键：symbol + market_type
        key = f"{symbol}_{market_type}"
        
        if key not in self.history:
            self.history[key] = []
        
        now = datetime.utcnow()
        timestamp = now.isoformat()
        
        # 添加新记录
        self.history[key].append({
            "timestamp": timestamp,
            "price": float(price)
        })
        
        # 清理过期数据
        self.cleanup_old_data(key, now)
        
        # 保存数据
        self.save_history()
    
    def cleanup_old_data(self, key, current_time):
        """清理超过最大保留时间的数据"""
        if key not in self.history:
            return
        
        # 计算最早保留的时间点
        cutoff_time = current_time - timedelta(hours=self.max_hours)
        
        # 过滤掉旧数据
        self.history[key] = [
            entry for entry in self.history[key]
            if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
        ]
    
    def get_price_changes(self, symbol, market_type, time_windows):
        """计算指定时间窗口内的价格变化"""
        key = f"{symbol}_{market_type}"
        
        if key not in self.history or not self.history[key]:
            return {}
        
        current_price = self.history[key][-1]["price"]
        current_time = datetime.fromisoformat(self.history[key][-1]["timestamp"])
        
        changes = {}
        
        # 遍历所有时间窗口
        for window in time_windows:
            # 确保 window 是整数
            if isinstance(window, str):
                try:
                    window = int(window)
                except ValueError:
                    logger.error(f"跳过无效的时间窗口: {window}")
                    continue
            
            # 计算窗口开始时间
            window_start = current_time - timedelta(minutes=window)
            
            # 找到窗口开始时间之后的最早价格
            for entry in self.history[key]:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if entry_time >= window_start:
                    start_price = entry["price"]
                    
                    # 检查价格有效性
                    if start_price <= 0:
                        continue
                        
                    price_change = ((current_price - start_price) / start_price) * 100
                    changes[window] = {
                        "start_price": start_price,
                        "current_price": current_price,
                        "change_percent": round(price_change, 2)
                    }
                    break
            else:
                # 如果没有找到足够的历史数据
                changes[window] = {
                    "start_price": None,
                    "current_price": current_price,
                    "change_percent": 0.0
                }
        
        return changes

class NotificationManager:
    """通知管理器（纯文本模式）"""
    def __init__(self, config, bot_state):
        self.config = config
        self.bot_state = bot_state
        self.last_update_id = 0  # 用于跟踪处理的最后一条更新
        self.user_state = {}  # 存储用户状态 {chat_id: {'state': '', 'data': {}}}
        self.setup_keyboard = {
            "keyboard": [
                ["1. 添加监控", "2. 删除监控"],
                ["3. 开启监控", "4. 停止监控"],
                ["5. 查看状态", "6. 帮助"]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
    
    def send_alert(self, symbol, market_type, window, change_data, threshold):
        """发送价格警报（纯文本模式）"""
        if not self.config.TELEGRAM_ENABLED:
            return
            
        message = self.create_alert_message(symbol, market_type, window, change_data, threshold)
        logger.info(f"ALERT: {message}")
        self.send_telegram(message)
    
    def send_startup_message(self, configs):
        """发送启动通知（纯文本模式）"""
        if not self.config.TELEGRAM_ENABLED or not self.config.STARTUP_NOTIFICATION:
            return
            
        message = self.create_startup_message(configs)
        logger.info(f"STARTUP: {message}")
        self.send_telegram(message)
    
    def create_alert_message(self, symbol, market_type, window, change_data, threshold):
        """创建警报消息（纯文本）"""
        change_percent = change_data["change_percent"]
        direction = "📈 上涨" if change_percent > 0 else "📉 下跌"
        abs_change = abs(change_percent)
        
        # 判断市场类型
        market_name = "永续合约" if market_type == "futures" else "现货"
        
        # 格式化价格
        start_price = f"{change_data['start_price']:,.4f}" if change_data['start_price'] else "N/A"
        current_price = f"{change_data['current_price']:,.4f}"
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        return (
            f"🚨 币安价格波动警报 ({market_name})\n"
            f"• 交易对: {symbol}\n"
            f"• 时间窗口: {window}分钟 (阈值: {threshold}%)\n"
            f"• 价格变化: {direction} {abs_change:.2f}%\n"
            f"• 起始价格: ${start_price}\n"
            f"• 当前价格: ${current_price}\n"
            f"• 时间: {current_time}"
        )
    
    def create_startup_message(self, configs):
        """创建启动消息 - 纯文本模式"""
        if not configs:
            return "⚠️ 没有监控配置，请添加监控配置"
        
        # 按币种和市场类型分组
        grouped_configs = {}
        for config in configs:
            key = (config["symbol"], config["market_type"])
            if key not in grouped_configs:
                grouped_configs[key] = []
            grouped_configs[key].append(config)
        
        # 构建消息
        message = "🚀 币安价格监控已启动\n\n"
        message += f"• 监控开始时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        message += f"• 监控配置数量: {len(configs)}\n"
        message += f"• 检查间隔: {self.config.CHECK_INTERVAL}秒\n\n"
        message += "🔔 当前监控配置:\n\n"
        
        for (symbol, market_type), configs in grouped_configs.items():
            market_name = "永续合约" if market_type == "futures" else "现货"
            message += f"🔹 {symbol} ({market_name}):\n"
            
            for config in configs:
                message += f"  - {config['window']}分钟: 阈值 {config['threshold']}%\n"
            
            message += "\n"
        
        return message
    
    def send_telegram(self, message, reply_markup=None):
        """发送Telegram通知（纯文本模式）"""
        try:
            url = f"https://api.telegram.org/bot{self.config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": self.config.TELEGRAM_CHAT_ID,
                "text": message
            }
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            # 添加代理支持
            proxies = {'https': Config.PROXY_URL} if Config.USE_PROXY and Config.PROXY_URL else None
            
            response = requests.post(url, json=payload, proxies=proxies, timeout=10)
            if response.status_code != 200:
                logger.error(f"Telegram发送失败: {response.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Telegram通知错误: {e}")
            return False
    
    def send_command_response(self, chat_id, message, reply_markup=None):
        """发送命令响应（纯文本模式）"""
        try:
            url = f"https://api.telegram.org/bot{self.config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message
            }
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            proxies = {'https': Config.PROXY_URL} if Config.USE_PROXY and Config.PROXY_URL else None
            response = requests.post(url, json=payload, proxies=proxies, timeout=10)
            if response.status_code != 200:
                logger.error(f"命令响应发送失败: {response.text}")
        except Exception as e:
            logger.error(f"发送命令响应错误: {e}")
    
    def process_commands(self):
        """处理Telegram命令"""
        try:
            url = f"https://api.telegram.org/bot{self.config.TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 30}
            
            proxies = {'https': Config.PROXY_URL} if Config.USE_PROXY and Config.PROXY_URL else None
            response = requests.get(url, params=params, proxies=proxies, timeout=35)
            
            if response.status_code != 200:
                logger.error(f"获取Telegram更新失败: {response.text}")
                return
            
            updates = response.json().get("result", [])
            if not updates:
                return
            
            for update in updates:
                self.last_update_id = update["update_id"]
                message = update.get("message")
                if not message:
                    continue
                
                chat_id = message["chat"]["id"]
                text = message.get("text", "").strip()
                
                # 只允许授权用户执行命令
                if str(chat_id) != str(self.config.TELEGRAM_CHAT_ID):
                    self.send_command_response(chat_id, "⚠️ 您无权执行此命令")
                    continue
                
                # 初始化用户状态
                if chat_id not in self.user_state:
                    self.user_state[chat_id] = {"state": "IDLE", "data": {}}
                
                # 处理交互式引导
                if self.user_state[chat_id]["state"] != "IDLE":
                    self.handle_guided_flow(chat_id, text)
                    continue
                
                # 处理数字命令
                command_mapping = {
                    "1": "添加监控",
                    "1. 添加监控": "添加监控",
                    "2": "删除监控",
                    "2. 删除监控": "删除监控",
                    "3": "开启监控",
                    "3. 开启监控": "开启监控",
                    "4": "停止监控",
                    "4. 停止监控": "停止监控",
                    "5": "查看状态",
                    "5. 查看状态": "查看状态",
                    "6": "帮助",
                    "6. 帮助": "帮助"
                }
                
                # 映射数字命令
                if text in command_mapping:
                    text = command_mapping[text]
                
                # 处理命令
                self.handle_command(chat_id, text)
        except Exception as e:
            logger.error(f"处理命令错误: {e}")
    
    def handle_guided_flow(self, chat_id, text):
        """处理交互式引导流程（纯文本模式）"""
        state = self.user_state[chat_id]["state"]
        data = self.user_state[chat_id]["data"]
        
        # 取消操作
        if text.lower() in ["取消", "exit", "quit", "/cancel"]:
            self.user_state[chat_id] = {"state": "IDLE", "data": {}}
            self.send_command_response(chat_id, "❌ 操作已取消", reply_markup=self.setup_keyboard)
            return
        
        try:
            # 添加监控流程 - 步骤1: 输入币种
            if state == "ADD_CONFIG_STEP1":
                # 验证币种格式（不允许带_PERP后缀）
                symbol = text.upper().strip()
                if "_PERP" in symbol:
                    self.send_command_response(chat_id, "⚠️ 请勿手动添加_PERP后缀，系统会自动处理")
                    return
                
                if not re.match(r"^[A-Z0-9]{5,12}$", symbol):
                    self.send_command_response(chat_id, "⚠️ 币种格式无效，请输入有效币种（如 BTCUSDT）")
                    return
                
                data["symbol"] = symbol
                self.user_state[chat_id]["state"] = "ADD_CONFIG_STEP2"
                self.send_command_response(chat_id, 
                    "📊 请选择交易类型:\n"
                    "1. 现货交易\n"
                    "2. 永续合约\n"
                    "回复数字选择", 
                    reply_markup={
                        "keyboard": [["1. 现货", "2. 永续合约"]],
                        "resize_keyboard": True,
                        "one_time_keyboard": True
                    }
                )
            
            # 步骤2: 选择交易类型
            elif state == "ADD_CONFIG_STEP2":
                if text in ["1", "1. 现货", "现货"]:
                    data["market_type"] = "spot"
                    self.user_state[chat_id]["state"] = "ADD_CONFIG_STEP3"
                    self.send_command_response(chat_id, "🕒 请输入监控时长（分钟）:")
                elif text in ["2", "2. 永续合约", "永续合约"]:
                    data["market_type"] = "futures"
                    self.user_state[chat_id]["state"] = "ADD_CONFIG_STEP3"
                    self.send_command_response(chat_id, "🕒 请输入监控时长（分钟）:")
                else:
                    self.send_command_response(chat_id, "⚠️ 请选择 '1. 现货' 或 '2. 永续合约'")
            
            # 步骤3: 输入监控时长
            elif state == "ADD_CONFIG_STEP3":
                # 验证监控时长
                try:
                    window = int(text)
                    if window <= 0:
                        raise ValueError
                except ValueError:
                    self.send_command_response(chat_id, "⚠️ 监控时长无效，请输入大于0的整数")
                    return
                
                data["window"] = window
                self.user_state[chat_id]["state"] = "ADD_CONFIG_STEP4"
                self.send_command_response(chat_id, "📈 请输入涨跌幅阈值（百分比，如 0.5）:")
            
            # 步骤4: 输入阈值
            elif state == "ADD_CONFIG_STEP4":
                # 验证阈值
                try:
                    threshold = float(text)
                    if threshold <= 0:
                        raise ValueError
                except ValueError:
                    self.send_command_response(chat_id, "⚠️ 阈值无效，请输入大于0的数字")
                    return
                
                data["threshold"] = threshold
                
                # 添加监控配置
                symbol = data["symbol"]
                market_type = data["market_type"]
                window = data["window"]
                threshold = data["threshold"]
                
                # 格式化交易对名称
                formatted_symbol = self.bot_state.get_formatted_symbol(symbol, market_type)
                
                # 添加配置
                result = self.bot_state.add_config(symbol, market_type, window, threshold)
                
                if result is None:
                    self.send_command_response(chat_id, 
                        f"⚠️ 已达到最大监控配置数量 ({self.config.MAX_MONITORING_CONFIGS})，无法添加更多配置")
                elif result:
                    response_msg = (
                        f"✅ 已添加监控配置\n"
                        f"• 交易对: {formatted_symbol}\n"
                        f"• 交易类型: {'永续合约' if market_type == 'futures' else '现货'}\n"
                        f"• 监控时长: {window}分钟\n"
                        f"• 涨跌幅阈值: {threshold:.2f}%"
                    )
                else:
                    response_msg = f"⚠️ {formatted_symbol} 在 {window}分钟 的监控配置已存在"
                
                self.send_command_response(chat_id, response_msg)
                
                # 询问是否继续添加
                self.user_state[chat_id]["state"] = "ADD_CONFIG_CONTINUE"
                self.send_command_response(chat_id, "❓ 是否继续添加其他监控配置？\n1. 是\n2. 否", reply_markup={
                    "keyboard": [["1. 是", "2. 否"]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                })
            
            # 步骤5: 是否继续添加
            elif state == "ADD_CONFIG_CONTINUE":
                if text in ["1", "1. 是", "是", "yes", "y"]:
                    self.user_state[chat_id] = {"state": "ADD_CONFIG_STEP1", "data": {}}
                    self.send_command_response(chat_id, "📝 请输入要监控的币种（如 BTCUSDT）:")
                elif text in ["2", "2. 否", "否", "no", "n"]:
                    self.user_state[chat_id] = {"state": "IDLE", "data": {}}
                    self.send_command_response(chat_id, "❓ 是否现在开启监控？\n1. 开启监控\n2. 暂不开启", reply_markup={
                        "keyboard": [["1. 开启监控", "2. 暂不开启"]],
                        "resize_keyboard": True,
                        "one_time_keyboard": True
                    })
                else:
                    self.send_command_response(chat_id, "⚠️ 请选择 '1. 是' 或 '2. 否'")
            
            # 处理开启监控选项
            elif state == "START_MONITOR_QUESTION":
                if text in ["1", "1. 开启监控", "开启监控"]:
                    self.bot_state.enable_monitoring()
                    
                    # 获取所有配置并发送状态
                    configs = self.bot_state.get_all_configs()
                    status_msg = self.create_startup_message(configs)
                    status_msg = "✅ 监控已开启\n\n" + status_msg
                    
                    self.send_command_response(chat_id, status_msg, reply_markup=self.setup_keyboard)
                elif text in ["2", "2. 暂不开启", "暂不开启"]:
                    self.send_command_response(chat_id, "⏸️ 监控未开启，您随时可以发送 '3' 开启监控", reply_markup=self.setup_keyboard)
                else:
                    self.send_command_response(chat_id, "⚠️ 请选择 '1. 开启监控' 或 '2. 暂不开启'")
                
                self.user_state[chat_id] = {"state": "IDLE", "data": {}}
            
            # 删除监控流程
            elif state == "REMOVE_CONFIG":
                # 获取所有配置
                configs = self.bot_state.get_all_configs()
                
                if not configs:
                    self.send_command_response(chat_id, "⚠️ 当前没有监控配置", reply_markup=self.setup_keyboard)
                    self.user_state[chat_id] = {"state": "IDLE", "data": {}}
                    return
                
                # 显示所有配置
                config_list = []
                for i, config in enumerate(configs):
                    formatted_symbol = self.bot_state.get_formatted_symbol(
                        config["symbol"], config["market_type"]
                    )
                    config_list.append(
                        f"{i+1}. {formatted_symbol} ({config['window']}分钟, 阈值 {config['threshold']}%)"
                    )
                
                config_list_str = "\n".join(config_list)
                
                self.user_state[chat_id]["state"] = "REMOVE_CONFIG_SELECT"
                self.user_state[chat_id]["data"] = {"configs": configs}
                
                self.send_command_response(chat_id, 
                    f"🔍 当前监控配置:\n{config_list_str}\n\n"
                    "请输入要删除的配置编号（输入 'all' 删除全部）:"
                )
            
            elif state == "REMOVE_CONFIG_SELECT":
                configs = self.user_state[chat_id]["data"]["configs"]
                
                if text.lower() == "all":
                    # 删除所有配置
                    self.bot_state.state["monitoring_configs"] = []
                    self.bot_state.save_state()
                    self.send_command_response(chat_id, "✅ 已删除所有监控配置", reply_markup=self.setup_keyboard)
                    self.user_state[chat_id] = {"state": "IDLE", "data": {}}
                    return
                
                try:
                    index = int(text) - 1
                    if 0 <= index < len(configs):
                        config = configs[index]
                        self.bot_state.remove_config(
                            config["symbol"], 
                            config["market_type"], 
                            config["window"]
                        )
                        
                        formatted_symbol = self.bot_state.get_formatted_symbol(
                            config["symbol"], config["market_type"]
                        )
                        
                        self.send_command_response(chat_id, 
                            f"✅ 已删除监控配置\n"
                            f"• 交易对: {formatted_symbol}\n"
                            f"• 时长: {config['window']}分钟\n"
                            f"• 阈值: {config['threshold']}%",
                            reply_markup=self.setup_keyboard
                        )
                    else:
                        self.send_command_response(chat_id, "⚠️ 无效的配置编号")
                        return
                except ValueError:
                    self.send_command_response(chat_id, "⚠️ 请输入有效的配置编号或 'all'")
                    return
                
                self.user_state[chat_id] = {"state": "IDLE", "data": {}}
        
        except Exception as e:
            logger.error(f"处理引导流程错误: {e}")
            self.user_state[chat_id] = {"state": "IDLE", "data": {}}
            self.send_command_response(chat_id, "⚠️ 处理过程中出错，已重置状态", reply_markup=self.setup_keyboard)
    
    def handle_command(self, chat_id, command):
        """处理具体命令（纯文本模式）"""
        try:
            # 帮助命令
            if command in ["/start", "/help", "6", "6. 帮助", "帮助"]:
                help_msg = (
                    "🤖 币安价格监控机器人\n\n"
                    "数字命令菜单:\n"
                    "1. 添加监控 - 添加新的监控配置\n"
                    "2. 删除监控 - 删除现有监控配置\n"
                    "3. 开启监控 - 启动价格监控\n"
                    "4. 停止监控 - 暂停价格监控\n"
                    "5. 查看状态 - 显示当前监控状态\n"
                    "6. 帮助 - 显示此帮助信息\n\n"
                    "⚠️ 注意: 每个币种可添加多个监控配置（不同时间段和阈值）"
                )
                self.send_command_response(chat_id, help_msg, reply_markup=self.setup_keyboard)
            
            # 查看状态
            elif command in ["/status", "5", "5. 查看状态", "查看状态"]:
                configs = self.bot_state.get_all_configs()
                status_msg = self.create_startup_message(configs)
                status = "✅ 监控已开启" if self.bot_state.is_monitoring_enabled() else "⛔ 监控已关闭"
                status_msg = f"📊 当前监控状态\n{status}\n\n" + status_msg
                self.send_command_response(chat_id, status_msg, reply_markup=self.setup_keyboard)
            
            # 开启监控
            elif command in ["/enable", "3", "3. 开启监控", "开启监控"]:
                self.bot_state.enable_monitoring()
                
                # 获取所有配置并发送状态
                configs = self.bot_state.get_all_configs()
                status_msg = self.create_startup_message(configs)
                status_msg = "✅ 监控已开启\n\n" + status_msg
                
                self.send_command_response(chat_id, status_msg, reply_markup=self.setup_keyboard)
            
            # 关闭监控
            elif command in ["/disable", "4", "4. 停止监控", "停止监控"]:
                self.bot_state.disable_monitoring()
                self.send_command_response(chat_id, "⛔ 监控已关闭", reply_markup=self.setup_keyboard)
            
            # 添加监控（进入引导流程）
            elif command in ["1", "1. 添加监控", "添加监控"]:
                self.user_state[chat_id] = {"state": "ADD_CONFIG_STEP1", "data": {}}
                self.send_command_response(chat_id, "📝 请输入要监控的币种（如 BTCUSDT）:")
            
            # 删除监控（进入引导流程）
            elif command in ["2", "2. 删除监控", "删除监控"]:
                configs = self.bot_state.get_all_configs()
                if not configs:
                    self.send_command_response(chat_id, "⚠️ 当前没有监控配置", reply_markup=self.setup_keyboard)
                    return
                
                self.user_state[chat_id] = {"state": "REMOVE_CONFIG", "data": {}}
                self.send_command_response(chat_id, "❌ 准备删除监控配置...")
            
            # 处理开启监控询问
            elif command in ["1. 开启监控", "开启监控", "3"]:
                self.bot_state.enable_monitoring()
                
                # 获取所有配置并发送状态
                configs = self.bot_state.get_all_configs()
                status_msg = self.create_startup_message(configs)
                status_msg = "✅ 监控已开启\n\n" + status_msg
                
                self.send_command_response(chat_id, status_msg, reply_markup=self.setup_keyboard)
            
            # 处理暂不开启监控
            elif command in ["2. 暂不开启", "暂不开启"]:
                self.send_command_response(chat_id, "⏸️ 监控未开启，您随时可以发送 '3' 开启监控", reply_markup=self.setup_keyboard)
            
            # 未知命令
            else:
                self.send_command_response(chat_id, "⚠️ 未知命令，请输入 '6' 查看帮助", reply_markup=self.setup_keyboard)
        except Exception as e:
            logger.error(f"处理命令 '{command}' 时出错: {e}")
            self.send_command_response(chat_id, "⚠️ 处理命令时出错，请重试", reply_markup=self.setup_keyboard)

class BinanceMonitor:
    """币安价格监控器（支持多币种多时间段多阈值）"""
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BinanceMonitor/1.0",
            "Accept": "application/json"
        })
        
        # 设置代理
        self.proxies = None
        if self.config.USE_PROXY and self.config.PROXY_URL:
            self.proxies = {'https': self.config.PROXY_URL}
            logger.info(f"使用代理: {self.config.PROXY_URL}")
        
        # 初始化状态管理
        self.bot_state = BotState(config)
        
        # 初始化组件
        self.price_history = PriceHistory()
        self.notifier = NotificationManager(config, self.bot_state)
        
        # 警报冷却时间 (避免重复通知)
        self.last_alert_time = {}
        self.alert_cooldown = 5 * 60  # 5分钟
        
        # 启动通知标志
        self.startup_notification_sent = False
        
        # 启动命令处理线程
        self.command_thread = threading.Thread(target=self.command_loop, daemon=True)
        self.command_thread.start()
    
    def command_loop(self):
        """命令处理循环"""
        logger.info("启动命令处理线程...")
        while True:
            try:
                self.notifier.process_commands()
                time.sleep(1)
            except Exception as e:
                logger.error(f"命令处理错误: {e}")
                time.sleep(5)
    
    def get_price(self, symbol, market_type):
        """获取指定交易对的价格"""
        try:
            if market_type == "futures":
                base_url = self.config.FUTURES_API_URL
                endpoint = "/fapi/v1/ticker/price"
            else:
                base_url = self.config.SPOT_API_URL
                endpoint = "/api/v3/ticker/price"
                
            url = f"{base_url}{endpoint}?symbol={symbol}"
            
            response = self.session.get(url, proxies=self.proxies, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            price = float(data['price'])
            
            # 检查价格有效性
            if price <= 0:
                logger.error(f"获取到无效价格: {symbol} {market_type} {price}")
                return None
                
            return price
        except Exception as e:
            logger.error(f"获取 {symbol} ({market_type}) 价格失败: {e}")
            return None
    
    def monitor_prices(self):
        """监控价格并检测波动"""
        # 获取监控配置
        configs = self.bot_state.get_all_configs()
        
        logger.info("=== 币安价格监控机器人启动 ===")
        logger.info(f"监控配置数量: {len(configs)}")
        
        # 记录配置详情
        for config in configs:
            formatted_symbol = self.bot_state.get_formatted_symbol(
                config["symbol"], config["market_type"]
            )
            logger.info(f"{formatted_symbol} - {config['window']}分钟窗口阈值: {config['threshold']}%")
        
        # 发送启动通知
        if self.config.TELEGRAM_ENABLED:
            logger.info("Telegram通知已启用")
            if not self.startup_notification_sent and self.config.STARTUP_NOTIFICATION:
                logger.info("尝试发送启动通知...")
                if self.notifier.send_startup_message(configs):
                    self.startup_notification_sent = True
                    logger.info("已发送启动通知")
                else:
                    logger.warning("启动通知发送失败")
        else:
            logger.info("Telegram通知未启用")
        
        while True:
            try:
                current_time = datetime.utcnow()
                logger.debug(f"监控周期开始: {current_time.strftime('%H:%M:%S UTC')}")
                
                # 检查监控状态
                if not self.bot_state.is_monitoring_enabled():
                    logger.info("监控已暂停")
                    time.sleep(self.config.CHECK_INTERVAL)
                    continue
                
                # 处理每个监控配置
                for config in configs:
                    symbol = config["symbol"]
                    market_type = config["market_type"]
                    
                    # 获取当前价格
                    price = self.get_price(symbol, market_type)
                    
                    if price is None:
                        logger.warning(f"无法获取 {symbol} ({market_type}) 价格，将重试")
                        continue
                    
                    # 添加到历史记录
                    self.price_history.add_price(symbol, market_type, price)
                    
                    # 计算价格变化
                    price_changes = self.price_history.get_price_changes(
                        symbol, 
                        market_type,
                        [config["window"]]  # 只需要当前配置的时间窗口
                    )
                    
                    # 检查是否需要发送警报
                    if config["window"] in price_changes:
                        self.check_for_alerts(
                            symbol, 
                            market_type,
                            config["window"],
                            price_changes[config["window"]],
                            config["threshold"]
                        )
                
                # 等待下一个监控周期
                time.sleep(self.config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("用户中断，退出程序")
                sys.exit(0)
            except Exception as e:
                logger.error(f"监控出错: {e}")
                time.sleep(30)  # 出错后等待30秒再重试
    
    def check_for_alerts(self, symbol, market_type, window, change_data, threshold):
        """检查价格变化是否超过阈值"""
        # 检查数据有效性
        if (
            change_data["start_price"] is None or 
            change_data["start_price"] <= 0 or
            change_data["current_price"] <= 0
        ):
            logger.debug(f"跳过无效数据: {symbol} {market_type} {window}分钟")
            return
            
        abs_change = abs(change_data["change_percent"])
        
        # 检查价格变化是否合理
        if abs_change > 1000:  # 超过1000%的变化通常不合理
            logger.warning(f"检测到异常价格波动: {symbol} {market_type} {window}分钟 {abs_change}%")
            return
            
        if abs_change >= threshold:
            # 检查冷却时间
            alert_key = f"{symbol}_{market_type}_{window}"
            current_time = time.time()
            last_alert = self.last_alert_time.get(alert_key, 0)
            
            if current_time - last_alert > self.alert_cooldown:
                # 发送警报
                self.notifier.send_alert(
                    symbol, 
                    market_type, 
                    window, 
                    change_data, 
                    threshold
                )
                self.last_alert_time[alert_key] = current_time

def main():
    """主函数"""
    try:
        config = Config()
        monitor = BinanceMonitor(config)
        monitor.monitor_prices()
    except Exception as e:
        logger.exception(f"程序启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
