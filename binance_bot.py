#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import logging
import requests
import threading
from datetime import datetime
from config import config  # 导入配置

# 设置日志记录器
def setup_logging():
    # 设置主日志记录器
    logger = logging.getLogger('BinanceMonitor')
    logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
    
    # 清除现有处理器
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # 创建格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器
    file_handler = logging.FileHandler('binance_monitor.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 减少其他库的日志输出
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
    
    return logger

# 初始化日志
logger = setup_logging()

class BotState:
    """机器人状态管理（支持多币种多时间段多阈值）"""
    def __init__(self):
        self.monitoring_enabled = True
        self.monitoring_configs = []
        
        # 加载保存的状态
        self.load_state()
        
        # 如果没有配置，使用默认配置
        if not self.monitoring_configs:
            self.set_default_config()
    
    def load_state(self):
        """从文件加载状态"""
        try:
            if os.path.exists(config.STATE_FILE):
                with open(config.STATE_FILE, 'r') as f:
                    state_data = json.load(f)
                    self.monitoring_enabled = state_data.get('monitoring_enabled', True)
                    self.monitoring_configs = state_data.get('monitoring_configs', [])
                    logger.info(f"已加载状态: {len(self.monitoring_configs)} 个监控配置")
        except Exception as e:
            logger.error(f"加载状态失败: {e}")
    
    def save_state(self):
        """保存状态到文件"""
        try:
            state_data = {
                'monitoring_enabled': self.monitoring_enabled,
                'monitoring_configs': self.monitoring_configs
            }
            with open(config.STATE_FILE, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")
    
    def set_default_config(self):
        """设置默认监控配置"""
        for symbol in config.DEFAULT_SYMBOLS:
            for window, threshold in config.DEFAULT_TIME_WINDOWS.items():
                self.add_monitoring_config(symbol, "spot", window, threshold)
        logger.info("已设置默认监控配置")
    
    def add_monitoring_config(self, symbol, market_type, window, threshold):
        """添加新的监控配置"""
        # 检查是否已存在相同配置
        for cfg in self.monitoring_configs:
            if (cfg['symbol'] == symbol and 
                cfg['market_type'] == market_type and 
                cfg['window'] == window):
                return False
        
        # 检查配置数量限制
        if len(self.monitoring_configs) >= config.MAX_MONITORING_CONFIGS:
            return False
        
        new_config = {
            'symbol': symbol,
            'market_type': market_type,
            'window': window,
            'threshold': threshold
        }
        self.monitoring_configs.append(new_config)
        self.save_state()
        return True
    
    def remove_monitoring_config(self, symbol, market_type, window):
        """移除监控配置"""
        self.monitoring_configs = [
            cfg for cfg in self.monitoring_configs
            if not (cfg['symbol'] == symbol and 
                    cfg['market_type'] == market_type and 
                    cfg['window'] == window)
        ]
        self.save_state()
        return True
    
    def enable_monitoring(self):
        """启用监控"""
        self.monitoring_enabled = True
        self.save_state()
        return True
    
    def disable_monitoring(self):
        """禁用监控"""
        self.monitoring_enabled = False
        self.save_state()
        return True
    
    def is_monitoring_enabled(self):
        """检查监控是否启用"""
        return self.monitoring_enabled
    
    def get_all_configs(self):
        """获取所有监控配置"""
        return self.monitoring_configs
    
    def get_formatted_symbol(self, symbol, market_type):
        """获取格式化后的交易对名称"""
        if market_type == "futures":
            return f"{symbol} (永续合约)"
        return f"{symbol} (现货)"

class PriceHistory:
    """价格历史数据管理"""
    def __init__(self):
        self.history = {}
    
    def add_price(self, symbol, market_type, price):
        """添加新的价格数据"""
        key = f"{symbol}_{market_type}"
        timestamp = time.time()
        
        if key not in self.history:
            self.history[key] = []
        
        # 添加新价格
        self.history[key].append((timestamp, price))
        
        # 清理旧数据
        self.clean_old_data(key)
    
    def clean_old_data(self, key):
        """清理超过24小时的数据"""
        max_age = config.MAX_HISTORY_HOURS * 3600  # 转换为秒
        current_time = time.time()
        
        # 保留最近24小时的数据
        self.history[key] = [
            (ts, price) for ts, price in self.history[key]
            if current_time - ts <= max_age
        ]
    
    def get_price_changes(self, symbol, market_type, windows):
        """计算指定时间窗口的价格变化"""
        key = f"{symbol}_{market_type}"
        current_time = time.time()
        result = {}
        
        if key not in self.history or not self.history[key]:
            return result
        
        # 获取当前价格（最新价格）
        current_price = self.history[key][-1][1]
        
        for window in windows:
            # 计算窗口开始时间（秒）
            window_seconds = window * 60
            window_start_time = current_time - window_seconds
            
            # 找到窗口开始时间之后的价格
            window_prices = [
                price for ts, price in self.history[key]
                if ts >= window_start_time
            ]
            
            if not window_prices:
                continue
            
            # 计算变化百分比
            start_price = window_prices[0]
            change = current_price - start_price
            change_percent = (change / start_price) * 100 if start_price != 0 else 0
            
            result[window] = {
                'start_price': start_price,
                'current_price': current_price,
                'change': change,
                'change_percent': change_percent
            }
        
        return result

class NotificationManager:
    """通知管理器"""
    def __init__(self, bot_state):
        self.bot_state = bot_state
        self.last_update_id = 0
        self.user_state = {}
        self.setup_keyboard = {
            "keyboard": [
                ["1. 添加监控", "2. 删除监控"],
                ["3. 开启监控", "4. 停止监控"],
                ["5. 查看状态", "6. 帮助"]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        self.cancel_keyboard = {
            "keyboard": [["0. 取消"]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        self.market_type_keyboard = {
            "keyboard": [
                ["现货", "永续合约"],
                ["0. 取消"]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        self.last_alert_log = {}
    
    def send_alert(self, symbol, market_type, window, change_data, threshold):
        """发送价格警报"""
        if not config.TELEGRAM_ENABLED:
            return False
            
        alert_key = f"{symbol}_{market_type}_{window}"
        current_time = time.time()
        
        # 检查冷却时间
        if alert_key in self.last_alert_log:
            last_alert_time, last_change = self.last_alert_log[alert_key]
            if (current_time - last_alert_time < config.ALERT_COOLDOWN and 
                (change_data["change_percent"] > 0) == (last_change > 0)):
                logger.debug(f"跳过重复警报: {alert_key}")
                return False
        
        message = self.create_alert_message(symbol, market_type, window, change_data, threshold)
        logger.info(f"ALERT: {message}")
        
        # 发送Telegram消息 - 增加重试机制
        success = False
        for attempt in range(3):
            success = self.send_telegram(message)
            if success:
                break
            logger.warning(f"警报发送失败，尝试 {attempt+1}/3")
            time.sleep(1)
        
        if success:
            self.last_alert_log[alert_key] = (current_time, change_data["change_percent"])
            return True
        return False
    
    def create_alert_message(self, symbol, market_type, window, change_data, threshold):
        """创建警报消息"""
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
    
    def send_telegram(self, message, chat_id=None, reply_markup=None):
        """发送Telegram通知"""
        try:
            if chat_id is None:
                # 使用验证过的 Chat ID
                chat_id = config.valid_chat_id
                if chat_id is None:
                    logger.error("无效的 Telegram Chat ID 配置")
                    return False
            else:
                # 确保命令处理中的 chat_id 是整数
                chat_id = int(chat_id)
                
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message
            }
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            # 添加代理支持
            proxies = {'https': config.PROXY_URL} if config.USE_PROXY and config.PROXY_URL else None
            
            # 增加超时时间
            response = requests.post(url, json=payload, proxies=proxies, timeout=15)
            
            # 记录详细的响应信息
            logger.debug(f"Telegram响应: {response.status_code}")
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram发送失败: {response.status_code} - {response.text}")
                return False
        except requests.exceptions.Timeout:
            logger.error("Telegram通知超时")
            return False
        except Exception as e:
            logger.error(f"Telegram通知错误: {str(e)}")
            return False
    
    def send_startup_message(self, configs):
        """发送启动通知"""
        if not config.TELEGRAM_ENABLED:
            return False
            
        message = "🟢 币安价格监控机器人已启动!\n\n"
        message += f"• 版本: 2.0\n"
        message += f"• 监控配置数量: {len(configs)}\n\n"
        message += "监控配置详情:\n"
        
        for cfg in configs:
            formatted_symbol = self.bot_state.get_formatted_symbol(
                cfg["symbol"], cfg["market_type"]
            )
            message += f"- {formatted_symbol}: {cfg['window']}分钟窗口 ({cfg['threshold']}%)\n"
        
        message += "\n监控已启动，将开始检测价格波动..."
        
        # 尝试发送启动消息，最多重试3次
        for attempt in range(3):
            if self.send_telegram(message):
                return True
            logger.warning(f"启动通知发送失败，尝试 {attempt+1}/3")
            time.sleep(2)
        
        return False
    
    def process_commands(self):
        """处理Telegram命令"""
        try:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 30
            }
            proxies = {'https': config.PROXY_URL} if config.USE_PROXY and config.PROXY_URL else None
            response = requests.get(url, params=params, proxies=proxies, timeout=35)
            
            if response.status_code != 200:
                logger.error(f"获取Telegram更新失败: {response.status_code}")
                return False
            
            data = response.json()
            if not data.get('ok'):
                return False

            updates = data.get('result', [])
            for update in updates:
                self.last_update_id = update['update_id']
                message = update.get('message')
                if not message:
                    continue
                chat_id = message['chat']['id']
                text = message.get('text', '').strip()
                
                # 处理命令
                if text == '/start' or text == '6. 帮助' or text == '/help':
                    self.send_help(chat_id)
                elif text == '1. 添加监控':
                    self.user_state[chat_id] = {'state': 'add_monitor_step1'}
                    self.send_telegram("请发送要监控的交易对（例如：BTCUSDT）:", chat_id, self.cancel_keyboard)
                elif text == '2. 删除监控':
                    self.user_state[chat_id] = {'state': 'remove_monitor_step1'}
                    self.send_monitoring_list(chat_id, True)
                elif text == '3. 开启监控':
                    self.bot_state.enable_monitoring()
                    self.send_telegram("✅ 监控已开启", chat_id)
                elif text == '4. 停止监控':
                    self.bot_state.disable_monitoring()
                    self.send_telegram("⛔ 监控已停止", chat_id)
                elif text == '5. 查看状态':
                    self.send_monitoring_list(chat_id)
                elif text == '0. 取消':
                    if chat_id in self.user_state:
                        del self.user_state[chat_id]
                    self.send_telegram("操作已取消", chat_id, self.setup_keyboard)
                elif chat_id in self.user_state:
                    self.handle_user_state(chat_id, text)
                
        except Exception as e:
            logger.error(f"处理命令错误: {e}")
        return True
    
    def handle_user_state(self, chat_id, text):
        """处理用户状态"""
        state = self.user_state[chat_id]['state']
        
        if state == 'add_monitor_step1':
            # 保存交易对
            self.user_state[chat_id] = {
                'state': 'add_monitor_step2',
                'symbol': text.upper()
            }
            self.send_telegram("请选择市场类型:", chat_id, self.market_type_keyboard)
        
        elif state == 'add_monitor_step2':
            # 保存市场类型
            if text == "现货":
                market_type = "spot"
            elif text == "永续合约":
                market_type = "futures"
            else:
                self.send_telegram("❌ 无效的市场类型，请选择 '现货' 或 '永续合约'", chat_id, self.market_type_keyboard)
                return
            
            self.user_state[chat_id] = {
                'state': 'add_monitor_step3',
                'symbol': self.user_state[chat_id]['symbol'],
                'market_type': market_type
            }
            self.send_telegram("请输入时间窗口（分钟，例如：5,15,60）:", chat_id, self.cancel_keyboard)
        
        elif state == 'add_monitor_step3':
            # 处理时间窗口
            try:
                windows = [int(w.strip()) for w in text.split(',')]
                self.user_state[chat_id]['windows'] = windows
                self.send_telegram("请输入阈值（%，例如：0.5,1.0,2.0）:", chat_id, self.cancel_keyboard)
                self.user_state[chat_id]['state'] = 'add_monitor_step4'
            except:
                self.send_telegram("❌ 无效的时间窗口格式，请使用逗号分隔的数字", chat_id, self.cancel_keyboard)
        
        elif state == 'add_monitor_step4':
            # 处理阈值
            try:
                thresholds = [float(t.strip()) for t in text.split(',')]
                symbol = self.user_state[chat_id]['symbol']
                market_type = self.user_state[chat_id]['market_type']
                windows = self.user_state[chat_id]['windows']
                
                if len(windows) != len(thresholds):
                    self.send_telegram("❌ 时间窗口和阈值数量不匹配", chat_id, self.cancel_keyboard)
                    return
                
                # 添加所有配置
                success_count = 0
                for window, threshold in zip(windows, thresholds):
                    if self.bot_state.add_monitoring_config(symbol, market_type, window, threshold):
                        success_count += 1
                
                # 清理用户状态
                del self.user_state[chat_id]
                
                # 发送结果
                if success_count > 0:
                    self.send_telegram(f"✅ 成功添加 {success_count} 个监控配置", chat_id, self.setup_keyboard)
                else:
                    self.send_telegram("❌ 添加监控配置失败，请重试", chat_id, self.setup_keyboard)
            except:
                self.send_telegram("❌ 无效的阈值格式，请使用逗号分隔的数字", chat_id, self.cancel_keyboard)
        
        elif state == 'remove_monitor_step1':
            # 处理删除监控
            try:
                index = int(text) - 1
                configs = self.bot_state.get_all_configs()
                
                if 0 <= index < len(configs):
                    config = configs[index]
                    if self.bot_state.remove_monitoring_config(
                        config['symbol'], config['market_type'], config['window']):
                        del self.user_state[chat_id]
                        self.send_telegram("✅ 监控配置已删除", chat_id, self.setup_keyboard)
                    else:
                        self.send_telegram("❌ 删除监控配置失败", chat_id, self.setup_keyboard)
                else:
                    self.send_telegram("❌ 无效的编号，请重试", chat_id)
            except:
                self.send_telegram("❌ 无效的输入，请输入配置编号", chat_id)
    
    def send_help(self, chat_id):
        """发送帮助信息"""
        help_text = (
            "📚 币安价格监控机器人帮助\n\n"
            "1. 添加监控 - 添加新的监控配置\n"
            "2. 删除监控 - 删除现有监控配置\n"
            "3. 开启监控 - 启动价格监控\n"
            "4. 停止监控 - 暂停价格监控\n"
            "5. 查看状态 - 查看当前监控配置\n"
            "6. 帮助 - 显示此帮助信息\n\n"
            "使用示例:\n"
            "添加 BTCUSDT 现货的监控:\n"
            "1. 选择 '1. 添加监控'\n"
            "2. 输入 BTCUSDT\n"
            "3. 选择 '现货'\n"
            "4. 输入时间窗口 (例如: 5,15,60)\n"
            "5. 输入阈值 (例如: 0.5,1.0,2.0)"
        )
        self.send_telegram(help_text, chat_id, self.setup_keyboard)
    
    def send_monitoring_list(self, chat_id, for_removal=False):
        """发送监控列表"""
        configs = self.bot_state.get_all_configs()
        if not configs:
            self.send_telegram("当前没有监控配置", chat_id, self.setup_keyboard)
            return
        
        message = "📋 当前监控配置:\n\n" if not for_removal else "请选择要删除的配置:\n\n"
        for i, config in enumerate(configs, 1):
            formatted_symbol = self.bot_state.get_formatted_symbol(
                config["symbol"], config["market_type"]
            )
            message += f"{i}. {formatted_symbol} - {config['window']}分钟 (阈值: {config['threshold']}%)\n"
        
        if for_removal:
            self.user_state[chat_id] = {'state': 'remove_monitor_step1'}
            self.send_telegram(message, chat_id, self.cancel_keyboard)
        else:
            message += f"\n监控状态: {'🟢 运行中' if self.bot_state.is_monitoring_enabled() else '🔴 已停止'}"
            self.send_telegram(message, chat_id, self.setup_keyboard)

class BinanceMonitor:
    """币安价格监控器"""
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False  # 禁用SSL验证（仅用于测试）
        self.session.headers.update({
            "User-Agent": "BinanceMonitor/1.0",
            "Accept": "application/json"
        })
        
        # 设置代理
        self.proxies = None
        if config.USE_PROXY and config.PROXY_URL:
            self.proxies = {'https': config.PROXY_URL}
            logger.info(f"使用代理: {config.PROXY_URL}")
        
        # 初始化状态管理
        self.bot_state = BotState()
        
        # 初始化组件
        self.price_history = PriceHistory()
        self.notifier = NotificationManager(self.bot_state)
        
        # 警报冷却时间
        self.last_alert_time = {}
        
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
                base_url = config.FUTURES_API_URL
                endpoint = "/fapi/v1/ticker/price"
            else:
                base_url = config.SPOT_API_URL
                endpoint = "/api/v3/ticker/price"
                
            url = f"{base_url}{endpoint}?symbol={symbol}"
            
            # 重试机制
            for attempt in range(3):
                try:
                    response = self.session.get(url, proxies=self.proxies, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    
                    if 'price' not in data:
                        logger.error(f"无效响应: {data}")
                        return None
                    
                    price = float(data['price'])
                    
                    if price <= 0:
                        logger.error(f"获取到无效价格: {symbol} {market_type} {price}")
                        return None
                        
                    return price
                except requests.exceptions.RequestException as e:
                    if attempt < 2:
                        logger.warning(f"获取价格失败 (尝试 {attempt+1}/3): {str(e)}")
                        time.sleep(1)
                    else:
                        logger.error(f"最终获取价格失败: {str(e)}")
                        return None
        except Exception as e:
            logger.error(f"获取 {symbol} ({market_type}) 价格失败: {str(e)}")
            return None
    
    def monitor_prices(self):
        """监控价格并检测波动"""
        configs = self.bot_state.get_all_configs()
        
        logger.info("=== 币安价格监控机器人启动 ===")
        logger.info(f"监控配置数量: {len(configs)}")
        
        for cfg in configs:
            formatted_symbol = self.bot_state.get_formatted_symbol(
                cfg["symbol"], cfg["market_type"]
            )
            logger.info(f"{formatted_symbol} - {cfg['window']}分钟窗口阈值: {cfg['threshold']}%")
        
        # 发送启动通知
        if config.TELEGRAM_ENABLED and not self.startup_notification_sent and config.STARTUP_NOTIFICATION:
            logger.info("尝试发送启动通知...")
            if self.notifier.send_startup_message(configs):
                self.startup_notification_sent = True
                logger.info("已发送启动通知")
            else:
                # 详细的错误诊断
                if config.valid_chat_id is None:
                    logger.error("启动通知发送失败: 无效的 Chat ID 配置")
                else:
                    logger.error("启动通知发送失败，请检查网络连接和 Telegram 配置")
        
        # 启动后立即发送一条测试消息
        if config.TELEGRAM_ENABLED and config.valid_chat_id:
            test_msg = "✅ 币安监控机器人已成功启动并运行!"
            if self.notifier.send_telegram(test_msg):
                logger.info("测试消息发送成功")
            else:
                logger.error("测试消息发送失败")
        
        while True:
            try:
                # 检查监控状态
                if not self.bot_state.is_monitoring_enabled():
                    time.sleep(config.CHECK_INTERVAL)
                    continue
                
                # 处理每个监控配置
                for cfg in configs:
                    symbol = cfg["symbol"]
                    market_type = cfg["market_type"]
                    
                    # 获取当前价格
                    price = self.get_price(symbol, market_type)
                    
                    if price is None:
                        continue
                    
                    # 添加到历史记录
                    self.price_history.add_price(symbol, market_type, price)
                    
                    # 计算价格变化
                    price_changes = self.price_history.get_price_changes(
                        symbol, market_type, [cfg["window"]]
                    )
                    
                    # 检查是否需要发送警报
                    if cfg["window"] in price_changes:
                        self.check_for_alerts(
                            symbol, market_type, cfg["window"],
                            price_changes[cfg["window"]], cfg["threshold"]
                        )
                
                # 等待下一个监控周期
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("用户中断，退出程序")
                sys.exit(0)
            except Exception as e:
                logger.error(f"监控出错: {str(e)}")
                time.sleep(30)
    
    def check_for_alerts(self, symbol, market_type, window, change_data, threshold):
        """检查价格变化是否超过阈值"""
        if (change_data["start_price"] is None or 
            change_data["start_price"] <= 0 or
            change_data["current_price"] <= 0):
            return
            
        abs_change = abs(change_data["change_percent"])
        
        if abs_change > 1000:  # 异常波动
            return
            
        if abs_change >= threshold:
            alert_key = f"{symbol}_{market_type}_{window}"
            current_time = time.time()
            last_alert = self.last_alert_time.get(alert_key, 0)
            
            logger.info(
                f"检测到波动: {symbol} ({market_type}) "
                f"{window}分钟变化 {abs_change:.2f}% (阈值: {threshold}%)"
            )
            
            if current_time - last_alert > config.ALERT_COOLDOWN:
                alert_sent = self.notifier.send_alert(
                    symbol, market_type, window, change_data, threshold
                )
                
                if alert_sent:
                    logger.info(f"警报发送成功: {symbol} {market_type} {window}分钟")
                    self.last_alert_time[alert_key] = current_time
                else:
                    logger.error(f"警报发送失败: {symbol} {market_type} {window}分钟")
            else:
                logger.info(f"冷却中: {symbol} {market_type} {window}分钟")

# 主函数
def main():
    """主函数"""
    try:
        monitor = BinanceMonitor()
        monitor.monitor_prices()
    except Exception as e:
        # 使用全局logger记录异常
        global logger
        logger.exception(f"程序启动失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
