# Deploy to DigitalOcean (Ubuntu 24.04)

## 1) SSH diagnostics from Windows

```powershell
ssh -vvv -o ConnectTimeout=10 root@209.38.246.50
```

If key auth is needed explicitly:

```powershell
ssh -i $HOME/.ssh/id_ed25519 -vvv -o ConnectTimeout=10 root@209.38.246.50
```

## 2) Fallback via DigitalOcean Console

Run on the droplet:

```bash
systemctl status ssh
ss -tulpn | grep :22 || true
ufw status
mkdir -p /root/.ssh && chmod 700 /root/.ssh
printf '%s\n' '<YOUR_PUBLIC_KEY>' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
systemctl restart ssh
```

## 3) Bot setup

```bash
apt update && apt install -y git
git clone <GITHUB_REPO_URL> /opt/xp-bot
chmod +x /opt/xp-bot/scripts/bootstrap_server.sh /opt/xp-bot/scripts/install_service.sh /opt/xp-bot/scripts/backup_db.sh
bash /opt/xp-bot/scripts/bootstrap_server.sh <GITHUB_REPO_URL>
nano /opt/xp-bot/.env
```

`.env` must contain:

```bash
BOT_TOKEN=from BotFather
ADMIN_IDS=from UserInfoID_Bot
```

## 4) systemd service

```bash
bash /opt/xp-bot/scripts/install_service.sh
journalctl -u xp-bot -f
```

## 5) Nightly SQLite backup

```bash
chmod +x /opt/xp-bot/scripts/backup_db.sh
(crontab -l 2>/dev/null; echo '0 3 * * * /opt/xp-bot/scripts/backup_db.sh') | crontab -
crontab -l
```
