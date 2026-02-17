# Deployment Configuration

This directory contains the configuration files and scripts required to deploy the Sports Card Dashboard to a Linux VPS.

## Files

- **`setup.sh`**: The main setup script. Run this on a fresh Ubuntu server to install dependencies, set up users, and deploy the application.
  - Usage: `sudo bash setup.sh <YOUR_DOMAIN>`

- **`nginx.conf`**: Nginx server block configuration. It sets up reverse proxying for the three environments:
  - **PROD** (`/`) -> Port 8501
  - **UAT** (`/uat`) -> Port 8502
  - **DEV** (`/dev`) -> Port 8503

- **Service Files**: Systemd unit files to manage the Streamlit application as background services.
  - **`card-dashboard-prod.service`**: Production environment.
  - **`card-dashboard-uat.service`**: UAT environment.
  - **`card-dashboard-dev.service`**: Development environment.

## Manual Management

To restart a specific environment:

```bash
sudo systemctl restart card-dashboard-prod
sudo systemctl restart card-dashboard-uat
sudo systemctl restart card-dashboard-dev
```

To view logs:

```bash
sudo journalctl -u card-dashboard-prod -f
```
