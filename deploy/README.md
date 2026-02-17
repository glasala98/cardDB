# Deployment Configuration and Guide

This directory contains the configuration files and scripts required to deploy the Sports Card Dashboard to a Linux VPS (Ubuntu).

## Directory Contents

| File | Description |
|------|-------------|
| `setup.sh` | Main installation script. Installs system dependencies (Python, Nginx, Certbot), creates the `cardapp` user, sets up the virtual environment, and configures the systemd service. |
| `nginx.conf` | Nginx server block configuration. Acts as a reverse proxy, forwarding traffic from port 80/443 to the Streamlit app on port 8501. |
| `card-dashboard.service` | Systemd unit file. Manages the Streamlit application as a background service, ensuring it starts on boot and restarts on failure. |

---

# Deployment Guide

Follow these steps to deploy the dashboard to a VPS (e.g., DigitalOcean, Hetzner, Linode).

## Step 1: Get a VPS

Sign up for a cheap Ubuntu VPS. Recommended specs:
- **OS:** Ubuntu 22.04 LTS
- **Plan:** Basic / Shared CPU (1GB RAM is sufficient for Streamlit alone, 2GB+ recommended if running scraper on server)

After creating it, note the **IP address** (e.g. `123.45.67.89`).

## Step 2: Configure DNS

Point your domain to the VPS IP address.
1. Log into your domain registrar (e.g., Porkbun, Namecheap).
2. Add an **A Record**:
   - **Host:** `@` (or blank)
   - **Value:** `123.45.67.89` (your VPS IP)
   - **TTL:** 600 (or default)
3. (Optional) Add a `www` CNAME or A record if desired.

Wait for DNS propagation (usually 5-30 minutes).

## Step 3: Deploy to VPS

### 3a. Copy files to server

From your local project **root directory**, run:

```bash
scp -r dashboard_prod.py card_prices_summary.csv requirements.txt deploy/ root@123.45.67.89:/root/
```

### 3b. SSH in and run setup

Login to your VPS and run the setup script:

```bash
ssh root@123.45.67.89
cd /root
sudo bash deploy/setup.sh yourdomain.com
```

**Replace `yourdomain.com` with your actual domain name.**

The script will:
- Install Python, Nginx, Certbot
- Create a virtualenv and install dependencies
- Set up Streamlit as a background service
- Configure Nginx as a reverse proxy
- Obtain a free SSL certificate from Let's Encrypt

Your site should now be live at `https://yourdomain.com`.

## Step 4: Update Data

The scraper is typically run locally. To push new price data to the server:

```bash
# From local project root
scp card_prices_summary.csv root@123.45.67.89:/opt/card-dashboard/

# Restart service to reload data
ssh root@123.45.67.89 "chown cardapp:cardapp /opt/card-dashboard/card_prices_summary.csv && sudo systemctl restart card-dashboard"
```

## Useful Commands (on the VPS)

```bash
# Check if the app is running
sudo systemctl status card-dashboard

# View live application logs
sudo journalctl -u card-dashboard -f

# Restart the app
sudo systemctl restart card-dashboard

# Check Nginx status
sudo systemctl status nginx
```

## Troubleshooting

**Site not loading?**
- Check DNS resolution: `nslookup yourdomain.com` (should match VPS IP)
- Check service status: `sudo systemctl status card-dashboard`
- Check firewall: `sudo ufw status` (ports 80 and 443 must be ALLOWED)

**502 Bad Gateway?**
- This usually means Nginx is running but cannot connect to Streamlit.
- Check Streamlit logs: `sudo journalctl -u card-dashboard --no-pager -n 50`
- Ensure Streamlit is running on port 8501.
