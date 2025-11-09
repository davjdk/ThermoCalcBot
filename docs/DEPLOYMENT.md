# ThermoCalcBot Deployment Guide

## 📋 Overview

This guide covers the complete deployment process for ThermoCalcBot, a Telegram bot for thermodynamic calculations.

### Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Nginx Proxy   │────│  ThermoCalcBot  │────│   Redis Cache   │
│   (Port 443)    │    │  (Port 8443)    │    │   (Port 6379)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
    SSL/TLS Termination   Application Logic   Session Storage
    Rate Limiting         Bot Implementation   Caching Layer
    Load Balancing        File Handling        Data Persistence
```

## 🚀 Quick Start

### Prerequisites

- Docker 20.10+ and Docker Compose v2.0+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An OpenRouter API key from [OpenRouter.ai](https://openrouter.ai/)
- A domain name (for production deployment)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/agents_for_david.git
   cd agents_for_david
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start the services**
   ```bash
   docker-compose up -d
   ```

4. **Verify the deployment**
   ```bash
   curl http://localhost/health
   ```

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram bot token from @BotFather |
| `TELEGRAM_BOT_USERNAME` | ✅ | Bot username (without @) |
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key for LLM access |
| `TELEGRAM_WEBHOOK_URL` | 🔄 | Webhook URL for production mode |
| `TELEGRAM_MODE` | ❌ | `polling` (default) or `webhook` |

### Production Configuration

For production deployment, use the provided production configuration files:

```bash
# Copy production environment template
cp .env.prod .env

# Edit with your production values
nano .env
```

Key production settings:
- `TELEGRAM_MODE=webhook`
- `MAX_CONCURRENT_USERS=100`
- `LOG_LEVEL=INFO`
- `ENABLE_USER_AUTH=true`

## 🐳 Docker Deployment

### Development Environment

```bash
# Use development configuration
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f thermo-telegram-bot
```

### Production Environment

```bash
# Production deployment
export ENVIRONMENT=production
docker-compose up -d

# Scale bot instances
docker-compose up -d --scale thermo-telegram-bot=3
```

### Service Management

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Update services
docker-compose pull
docker-compose up -d
```

## 🔒 SSL/TLS Setup

### Automatic with Let's Encrypt

```bash
# Setup SSL with Let's Encrypt
export DOMAIN=your-domain.com
export EMAIL=admin@your-domain.com
./scripts/setup_ssl.sh letsencrypt
```

### Manual SSL Certificate Setup

```bash
# Create self-signed certificate for testing
./scripts/setup_ssl.sh self-signed

# Place your certificates in nginx/ssl/
cp your-cert.pem nginx/ssl/cert.pem
cp your-key.pem nginx/ssl/key.pem
```

### SSL Renewal (Let's Encrypt)

Let's Encrypt certificates are automatically renewed. To check renewal:

```bash
# Check certificate status
certbot certificates

# Test renewal
certbot renew --dry-run
```

## 🔧 Configuration Management

### Environment-Specific Configurations

The project supports multiple environments:

- **Development**: `.env.dev` - Debug logging, relaxed limits
- **Staging**: `.env.staging` - Production-like features, test data
- **Production**: `.env.prod` - Full security, optimized performance

### Configuration Validation

```bash
# Test configuration
python -c "
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
config = TelegramBotConfig.from_env()
errors = config.validate()
if errors:
    print('Configuration errors:', errors)
else:
    print('Configuration is valid')
"
```

## 📊 Monitoring and Logging

### Health Checks

```bash
# Bot health check
curl http://localhost/health

# Nginx status
curl http://localhost/nginx_status

# Docker health check
docker-compose exec thermo-telegram-bot curl http://localhost:8443/health
```

### Log Management

```bash
# View application logs
docker-compose logs -f thermo-telegram-bot

# View nginx logs
docker-compose logs -f nginx

# View redis logs
docker-compose logs -f redis

# Access log files
ls -la logs/
```

### Metrics Collection

Enable metrics collection by setting:
```bash
ENABLE_METRICS=true
METRICS_EXPORT_INTERVAL=60
```

Access metrics at: `http://localhost/metrics`

## 🔒 Security Considerations

### Network Security

1. **Firewall Configuration**
   ```bash
   # Allow only necessary ports
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw deny 8443/tcp  # Bot should only be accessible via Nginx
   ```

2. **SSL/TLS**
   - Always use HTTPS in production
   - Implement HSTS headers
   - Use strong cipher suites

3. **Bot Security**
   - Validate all incoming requests
   - Implement rate limiting
   - Sanitize user inputs

### Secret Management

```bash
# Use environment variables for secrets
export TELEGRAM_BOT_TOKEN="your-secret-token"
export OPENROUTER_API_KEY="your-secret-key"

# Never commit secrets to version control
echo ".env" >> .gitignore
echo "*.key" >> .gitignore
echo "*.pem" >> .gitignore
```

## 🔄 Backup and Recovery

### Automated Backups

```bash
# Create backup
./scripts/backup.sh full

# Schedule daily backups
echo "0 2 * * * /opt/thermo-bot/scripts/backup.sh full" | crontab -

# List backups
ls -la /backup/thermo-bot/
```

### Manual Backup

```bash
# Backup specific components
./scripts/backup.sh database    # Database only
./scripts/backup.sh config      # Configuration only
./scripts/backup.sh logs        # Logs only
```

### Recovery

```bash
# Restore from backup
docker-compose down
./scripts/restore.sh /backup/thermo-bot/backup_20231201_020000
docker-compose up -d
```

## 🚨 Troubleshooting

### Common Issues

1. **Bot Not Responding**
   ```bash
   # Check bot logs
   docker-compose logs thermo-telegram-bot

   # Verify bot token
   curl -H "Authorization: Bearer $TELEGRAM_BOT_TOKEN" \
        https://api.telegram.org/bot/getMe
   ```

2. **SSL Certificate Issues**
   ```bash
   # Check certificate validity
   openssl x509 -in nginx/ssl/cert.pem -noout -dates

   # Test SSL configuration
   nginx -t
   ```

3. **Database Connection Issues**
   ```bash
   # Check database file
   ls -la data/thermo_data.db

   # Test database access
   sqlite3 data/thermo_data.db ".tables"
   ```

4. **High Memory Usage**
   ```bash
   # Check memory usage
   docker stats

   # Restart services if needed
   docker-compose restart
   ```

### Performance Optimization

1. **Database Optimization**
   ```bash
   # Optimize SQLite database
   sqlite3 data/thermo_data.db "VACUUM;"

   # Analyze query performance
   sqlite3 data/thermo_data.db "EXPLAIN QUERY PLAN SELECT * FROM compounds LIMIT 10;"
   ```

2. **Cache Optimization**
   ```bash
   # Check Redis memory usage
   docker-compose exec redis redis-cli info memory

   # Clear cache if needed
   docker-compose exec redis redis-cli FLUSHALL
   ```

## 📋 Deployment Checklist

### Pre-Deployment Checklist

- [ ] Environment variables configured
- [ ] SSL certificates installed
- [ ] DNS records pointing to server
- [ ] Firewall rules configured
- [ ] Backup procedures tested
- [ ] Monitoring enabled
- [ ] Log rotation configured

### Post-Deployment Verification

- [ ] Health checks passing
- [ ] Bot responding to commands
- [ ] SSL certificate valid
- [ ] Metrics collecting
- [ ] Logs properly written
- [ ] Backup created

## 🆘 Support

### Getting Help

1. **Documentation**: Check the [main documentation](../README.md)
2. **Issues**: Open an issue on [GitHub](https://github.com/your-org/agents_for_david/issues)
3. **Logs**: Collect logs from `logs/` directory
4. **Health Check**: Run `curl http://localhost/health`

### Community

- **Telegram**: Join our [Telegram group](https://t.me/thermocalc_support)
- **Discussions**: Participate in [GitHub Discussions](https://github.com/your-org/agents_for_david/discussions)
- **Wiki**: Check the [project wiki](https://github.com/your-org/agents_for_david/wiki)

---

**Last Updated**: December 2024
**Version**: 1.1.0