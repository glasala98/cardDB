# Deploying the Hockey Card Dashboard

## Overview

This runs your Streamlit dashboard on a VPS with your Porkbun domain.
The scraper stays local — you run it on your PC and upload the CSV to the server.

---

## Step 1: Get a VPS

Sign up for a cheap Ubuntu VPS. Recommended:
- **DigitalOcean** ($6/mo) — Create a Droplet: Ubuntu 22.04, Basic, Regular CPU, $6/mo
- **Hetzner** ($4/mo) — Cheapest option, EU-based
- **Linode** ($5/mo)

Pick the smallest tier — Streamlit is lightweight without Selenium.

After creating it, note the **IP address** (e.g. `123.45.67.89`).

---

## Step 2: Point Your Porkbun Domain

1. Log into [Porkbun](https://porkbun.com)
2. Go to **Domain Management** > click your domain
3. Click **DNS Records**
4. Delete any existing A records
5. Add a new record:
   - **Type:** A
   - **Host:** (leave blank for root domain, or `www` for subdomain)
   - **Answer:** `123.45.67.89` (your VPS IP)
   - **TTL:** 600
6. If you want `www` too, add another A record with Host = `www`

DNS can take 5-30 minutes to propagate.

---

## Step 3: Deploy to VPS

### 3a. Copy files to server

From your local CardAnalysis folder, run:

```bash
scp -r dashboard_prod.py card_prices_summary.csv requirements.txt deploy/ root@123.45.67.89:/root/
```

### 3b. SSH in and run setup

```bash
ssh root@123.45.67.89
cd /root
sudo bash deploy/setup.sh yourdomain.com
```

Replace `yourdomain.com` with your actual domain.

The script will:
- Install Python, Nginx, Certbot
- Create a virtualenv and install dependencies
- Set up Streamlit as a background service
- Configure Nginx as a reverse proxy
- Get a free SSL certificate from Let's Encrypt

Your site should now be live at `https://yourdomain.com`

---

## Step 4: Update Data (after scraping locally)

When you run the scraper on your PC and want to push new data:

```bash
scp card_prices_summary.csv root@123.45.67.89:/opt/card-dashboard/
ssh root@123.45.67.89 "chown cardapp:cardapp /opt/card-dashboard/card_prices_summary.csv && sudo systemctl restart card-dashboard"
```

---

## Useful Commands (on the VPS)

```bash
# Check if the app is running
sudo systemctl status card-dashboard

# View live logs
sudo journalctl -u card-dashboard -f

# Restart the app
sudo systemctl restart card-dashboard

# Renew SSL (auto-renews, but manual if needed)
sudo certbot renew
```

---

## Troubleshooting

**Site not loading?**
- Check DNS: `nslookup yourdomain.com` — should show your VPS IP
- Check service: `sudo systemctl status card-dashboard`
- Check nginx: `sudo nginx -t && sudo systemctl status nginx`
- Check firewall: `sudo ufw status` — ports 80 and 443 should be open

**502 Bad Gateway?**
- Streamlit might not be running: `sudo systemctl restart card-dashboard`
- Check logs: `sudo journalctl -u card-dashboard --no-pager -n 50`
