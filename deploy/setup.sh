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
apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx ufw

# 2. Create app user
echo "--- Creating app user ---"
id -u $APP_USER &>/dev/null || useradd --system --no-create-home --shell /bin/false $APP_USER

# 3. Set up app directory
echo "--- Setting up app directory ---"
mkdir -p $APP_DIR
cp dashboard_prod.py $APP_DIR/
cp card_prices_summary.csv $APP_DIR/
cp requirements.txt $APP_DIR/
chown -R $APP_USER:$APP_USER $APP_DIR

# 4. Python virtual environment
echo "--- Creating Python venv ---"
python3 -m venv $APP_DIR/venv
$APP_DIR/venv/bin/pip install --upgrade pip
$APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

# 5. Systemd service
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
