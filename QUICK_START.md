# ThermoCalcBot - Quick Start Guide

## 🚀 5-Minute Deployment

### Prerequisites
- Docker and Docker Compose
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- OpenRouter API Key from [OpenRouter.ai](https://openrouter.ai/)

### Step 1: Get Your Tokens

1. **Create Telegram Bot**:
   - Message [@BotFather](https://t.me/BotFather) `/newbot`
   - Choose name: `ThermoCalcBot`
   - Choose username: `YourThermoBot`
   - Copy the bot token

2. **Get OpenRouter API Key**:
   - Sign up at [OpenRouter.ai](https://openrouter.ai/)
   - Go to API Keys section
   - Create and copy your API key

### Step 2: Deploy

```bash
# Clone the repository
git clone https://github.com/your-org/agents_for_david.git
cd agents_for_david

# Configure environment
cp .env.example .env
nano .env  # Add your tokens

# Start the bot
docker-compose up -d

# Check if it's working
curl http://localhost/health
```

### Step 3: Test Your Bot

1. Find your bot on Telegram: `@YourThermoBot`
2. Send `/start` command
3. Try a calculation: `Calculate H2O combustion enthalpy`

## 🔧 Environment Configuration

Edit `.env` file with your settings:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_BOT_USERNAME=YourThermoBot
OPENROUTER_API_KEY=your_openrouter_key_here

# Optional
MAX_CONCURRENT_USERS=20
LOG_LEVEL=INFO
ENABLE_FILE_DOWNLOADS=true
```

## 📡 Production Setup

For production deployment:

```bash
# Use production configuration
cp .env.prod .env
# Edit with your production settings

# Setup SSL
./scripts/setup_ssl.sh letsencrypt

# Deploy with health checks
export ENVIRONMENT=production
./scripts/deploy_production.sh
```

## 🐛 Troubleshooting

**Bot not responding?**
```bash
# Check logs
docker-compose logs thermo-telegram-bot

# Check configuration
python -c "from src.thermo_agents.telegram_bot.config import TelegramBotConfig; print(TelegramBotConfig.from_env().validate())"
```

**Health check failing?**
```bash
# Verify services
docker-compose ps

# Check bot health
curl http://localhost:8443/health
```

## 📚 Next Steps

- [Full Deployment Guide](docs/DEPLOYMENT.md)
- [Configuration Reference](docs/specs/telegram_bot_integration/06_configuration_deployment.md)
- [API Documentation](docs/API.md)

## 🆘 Need Help?

- Open a [GitHub Issue](https://github.com/your-org/agents_for_david/issues)
- Join our [Telegram Support](https://t.me/thermocalc_support)

---

**Happy calculating! 🧪⚗️**