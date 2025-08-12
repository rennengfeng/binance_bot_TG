class Config:
    # 调试模式
    DEBUG = True
    
    # 默认监控币种（格式：币种名称_PERP 表示永续合约）
    DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    
    # 默认时间窗口和阈值（分钟: 百分比）
    DEFAULT_TIME_WINDOWS = {
        5: 0.5,    # 5分钟窗口阈值 0.5%
        15: 1.5,   # 15分钟窗口阈值 1.5%
        60: 3.0    # 60分钟窗口阈值 3.0%
    }
    
    # 价格检查间隔（秒）
    CHECK_INTERVAL = 60
    
    # Telegram 配置
    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
    TELEGRAM_ENABLED = True
    STARTUP_NOTIFICATION = True
    
    # 代理设置
    USE_PROXY = False
    PROXY_URL = "http://your-proxy-ip:port"  # 例如 "http://127.0.0.1:1080"
    
    # 数据存储
    DATA_FILE = "price_history.json"
    MAX_HISTORY_HOURS = 24  # 历史数据保留时间（小时）
    
    # Binance API 地址
    SPOT_API_URL = "https://api.binance.com"
    FUTURES_API_URL = "https://fapi.binance.com"
    
    # 监控配置
    MAX_MONITORING_CONFIGS = 50  # 最大监控配置数量
