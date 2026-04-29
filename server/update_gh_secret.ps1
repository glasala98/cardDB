# =============================================================================
# Update GitHub Actions DATABASE_URL secret to point at local PostgreSQL
#
# Run after Tailscale is set up and local DB is verified.
#
# Usage:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\server\update_gh_secret.ps1
# =============================================================================

# ── Fill these in ─────────────────────────────────────────────────────────────
$TAILSCALE_IP  = "YOUR_TAILSCALE_IP"       # output of: tailscale ip -4
$PG_PASSWORD   = "YOUR_POSTGRES_PASSWORD"
# ─────────────────────────────────────────────────────────────────────────────

$NEW_URL = "postgresql://postgres:$PG_PASSWORD@${TAILSCALE_IP}:5432/carddb"

Write-Host "Updating GitHub Actions DATABASE_URL secret..." -ForegroundColor Yellow
Write-Host "  New URL: postgresql://postgres:****@${TAILSCALE_IP}:5432/carddb"

gh secret set DATABASE_URL --body $NEW_URL

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Secret updated." -ForegroundColor Green
    Write-Host ""
    Write-Host "GH Actions elite/staple workflows will now write to your local DB."
    Write-Host "Make sure your PC is on and Tailscale is running when those run."
} else {
    Write-Host "ERROR: gh CLI not found or not authenticated." -ForegroundColor Red
    Write-Host "Install gh: winget install GitHub.cli  then  gh auth login"
}
