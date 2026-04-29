# =============================================================================
# CardDB Local Setup — run this on your Windows PC after pg_dump completes
#
# Fill in the two variables below, then run:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\server\local_setup.ps1
# =============================================================================

# ── Fill these in ─────────────────────────────────────────────────────────────
$PG_PASSWORD   = "YOUR_POSTGRES_PASSWORD"   # password you set during PostgreSQL install
$DUMP_FILE     = "C:\Users\gerri\carddb_backup.dump"
# ─────────────────────────────────────────────────────────────────────────────

$PG_BIN  = "C:\Program Files\PostgreSQL\15\bin"
$PG_DATA = "C:\Program Files\PostgreSQL\15\data"
$env:PGPASSWORD = $PG_PASSWORD

Write-Host ""
Write-Host "=== CardDB Local Setup ===" -ForegroundColor Cyan

# ── 1. Create database ────────────────────────────────────────────────────────
Write-Host "`n[1/4] Creating local database..." -ForegroundColor Yellow
& "$PG_BIN\psql.exe" -U postgres -c "CREATE DATABASE carddb;" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Database may already exist, continuing..." -ForegroundColor Gray
}

# ── 2. Restore dump ───────────────────────────────────────────────────────────
Write-Host "`n[2/4] Restoring dump (this may take 5-15 minutes)..." -ForegroundColor Yellow
& "$PG_BIN\pg_restore.exe" -U postgres -d carddb -Fc --no-owner --no-privileges $DUMP_FILE
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: restore failed. Check the dump file path." -ForegroundColor Red
    exit 1
}
Write-Host "  Restore complete." -ForegroundColor Green

# ── 3. Configure PostgreSQL to accept Tailscale connections ───────────────────
Write-Host "`n[3/4] Configuring PostgreSQL for Tailscale access..." -ForegroundColor Yellow

# pg_hba.conf — allow connections from Tailscale IP range (100.64.0.0/10)
$hba = "$PG_DATA\pg_hba.conf"
$tailscaleRule = "host    carddb    postgres    100.64.0.0/10    md5"
$hbaContent = Get-Content $hba -Raw
if ($hbaContent -notlike "*100.64.0.0/10*") {
    Add-Content $hba "`n# Tailscale — allow scraper servers`n$tailscaleRule"
    Write-Host "  Added Tailscale rule to pg_hba.conf" -ForegroundColor Green
} else {
    Write-Host "  Tailscale rule already in pg_hba.conf" -ForegroundColor Gray
}

# postgresql.conf — listen on all interfaces (Tailscale + localhost)
$pgconf = "$PG_DATA\postgresql.conf"
$pgContent = Get-Content $pgconf -Raw
if ($pgContent -match "^#?listen_addresses\s*=") {
    $pgContent = $pgContent -replace "^#?listen_addresses\s*=.*", "listen_addresses = '*'"
    Set-Content $pgconf $pgContent
    Write-Host "  Updated listen_addresses in postgresql.conf" -ForegroundColor Green
}

# ── 4. Restart PostgreSQL ─────────────────────────────────────────────────────
Write-Host "`n[4/4] Restarting PostgreSQL..." -ForegroundColor Yellow
$svc = Get-Service -Name "postgresql*" | Select-Object -First 1
if ($svc) {
    Restart-Service $svc.Name
    Write-Host "  PostgreSQL restarted ($($svc.Name))" -ForegroundColor Green
} else {
    Write-Host "  Could not find PostgreSQL service — restart it manually in Services." -ForegroundColor Red
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Local setup complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Run Tailscale and note your IP:  tailscale ip -4"
Write-Host "  2. Paste that IP when running server/deploy.sh on each Hetzner server"
Write-Host "  3. Update .env in this repo:"
Write-Host "       DATABASE_URL=postgresql://postgres:$PG_PASSWORD@localhost:5432/carddb"
Write-Host "  4. Update GitHub Actions secret (run server/update_gh_secret.ps1)"
Write-Host "  5. Delete the Railway PostgreSQL service once verified"
Write-Host ""

# Quick verification
Write-Host "Verifying local DB..." -ForegroundColor Yellow
$result = & "$PG_BIN\psql.exe" -U postgres -d carddb -t -c "SELECT COUNT(*) FROM card_catalog;" 2>&1
Write-Host "  card_catalog rows: $($result.Trim())" -ForegroundColor Cyan
