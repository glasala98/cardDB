#!/bin/bash
# ============================================================
# Hockey Card Dashboard - VPS Setup Script
# Run as root on a fresh Ubuntu 22.04+ VPS
# Usage: sudo bash setup.sh YOUR_DOMAIN
# ============================================================

set -e

DOMAIN="${1:?Usage: sudo bash setup.sh YOUR_DOMAIN}"
APP_DIR="/opt/card-dashboard"
APP_USER="cardapp"

echo "=== Setting up Card Dashboard for ${DOMAIN} ==="

# 1. System packages
echo "--- Installing system packages ---"
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx ufw wget gnupg

# 1b. Install Chrome for Selenium (eBay scraping)
if ! command -v google-chrome &>/dev/null; then
    echo "--- Installing Google Chrome ---"
    wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    apt-get install -y /tmp/chrome.deb || apt-get -f install -y
    rm -f /tmp/chrome.deb
fi

# 2. Create app user
echo "--- Creating app user ---"
id -u $APP_USER &>/dev/null || useradd --system --no-create-home --shell /bin/false $APP_USER

# 3. Set up app directory
echo "--- Setting up app directory ---"
mkdir -p $APP_DIR
cp dashboard_prod.py $APP_DIR/
cp dashboard_utils.py $APP_DIR/
cp scrape_card_prices.py $APP_DIR/
cp card_prices_summary.csv $APP_DIR/
cp -f card_prices_results.json $APP_DIR/ 2>/dev/null || true
cp -f price_history.json $APP_DIR/ 2>/dev/null || true
cp requirements.txt $APP_DIR/
chown -R $APP_USER:$APP_USER $APP_DIR

# 4. Python virtual environment
echo "--- Creating Python venv ---"
python3 -m venv $APP_DIR/venv
$APP_DIR/venv/bin/pip install --upgrade pip
$APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

# 5. Environment file for API keys
if [ ! -f $APP_DIR/.env ]; then
    echo "--- Creating .env file ---"
    echo 'ANTHROPIC_API_KEY=your-key-here' > $APP_DIR/.env
    chown $APP_USER:$APP_USER $APP_DIR/.env
    chmod 600 $APP_DIR/.env
    echo "IMPORTANT: Edit /opt/card-dashboard/.env with your real ANTHROPIC_API_KEY"
fi

# 6. Systemd service
echo "--- Installing systemd service ---"
cp deploy/card-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable card-dashboard
systemctl start card-dashboard

# 6. Nginx config
echo "--- Configuring Nginx ---"
sed "s/YOUR_DOMAIN/${DOMAIN}/g" deploy/nginx.conf > /etc/nginx/sites-available/card-dashboard
ln -sf /etc/nginx/sites-available/card-dashboard /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# 7. Firewall
echo "--- Configuring firewall ---"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 8. SSL certificate
echo "--- Getting SSL certificate ---"
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email

echo ""
echo "=== DONE! ==="
echo "Your dashboard is live at: https://${DOMAIN}"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status card-dashboard   # Check status"
echo "  sudo systemctl restart card-dashboard   # Restart app"
echo "  sudo journalctl -u card-dashboard -f    # View logs"
