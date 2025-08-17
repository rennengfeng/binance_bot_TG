# binance_bot_TG-引导版
监控币种、时间、阈值均在tg_bot上设置

## 要求
**Python 3.8 或更高（推荐3.10）**

## 使用方法
1.**克隆仓库：**

   ```bash
   git clone https://github.com/rennengfeng/Binance_bot.git
   ```
   ```bash
   cd Binance_bot
   ```

2.**安装依赖：**

   ```bash
   pip install -r requirements.txt
   ```

3.**设置：**

编辑`config.py`文件：

 ```bash
   nano config.py
   ```

设置要监控的交易对 (SYMBOLS)

调整监控间隔 (CHECK_INTERVAL)，单位秒

设置价格波动阈值 (PRICE_CHANGE_THRESHOLD)，单位百分比

配置时间窗口 (TIME_WINDOWS)，单位分钟

如果需要通知，配置 Telegram（token id） 设置

如果服务器需要代理访问币安，配置代理 (USE_PROXY 和 PROXY_URL)

4.**运行机器人：**

   ```bash
   python3 binance_bot.py #或者 python binance_bot.py
   ```

## 功能特点
多交易对监控：同时监控多个加密货币交易对

灵活的时间窗口：支持自定义多个时间窗口（如5分钟、15分钟、1小时）

智能警报：

超过阈值时发送通知

警报冷却机制避免消息轰炸

历史数据存储：自动保存价格历史，支持24小时数据分析

这个监控机器人可以7x24小时运行，当价格在设定时间窗口内波动超过阈值时，会立即发送警报通知，帮助您及时把握市场机会。

# TG机器人设置

## 创建机器人 

在 Telegram 中搜索 @userinfobot

点击 "Start" 或发送 /start 消息

输入名称，创建，获取Token

## 获取ID

   ```bash
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   替换 <YOUR_BOT_TOKEN> 为您的实际 Bot Token
   
   先给 Bot 发送一条消息
   
   刷新浏览器页面
   
   在 JSON 响应中查找 "chat":{"id":xxxxxxxx}
