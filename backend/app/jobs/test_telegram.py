from app.worker import send_telegram

if __name__ == '__main__':
    ok = send_telegram('✅ Hyper Wallet Tracker Telegram test message')
    print({'sent': ok})
