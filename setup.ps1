# ADF MCP Server — Setup Script
# Run this once after cloning the repository.
# Usage: .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ADF MCP Server — Environment Setup   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ──────────────────────────────────────────────────────────────
Write-Host "Checking Python..." -NoNewline
try {
    $pyVersion = python --version 2>&1
    Write-Host " $pyVersion" -ForegroundColor Green
} catch {
    Write-Host " NOT FOUND" -ForegroundColor Red
    Write-Host "Please install Python 3.9+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# ── Create virtual environment ─────────────────────────────────────────────────
if (Test-Path ".venv") {
    Write-Host "Virtual environment already exists — skipping creation." -ForegroundColor Yellow
} else {
    Write-Host "Creating virtual environment..." -NoNewline
    python -m venv .venv
    Write-Host " Done" -ForegroundColor Green
}

# ── Activate venv ─────────────────────────────────────────────────────────────
Write-Host "Activating virtual environment..." -NoNewline
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force
& .\.venv\Scripts\Activate.ps1
Write-Host " Done" -ForegroundColor Green

# ── Install dependencies ───────────────────────────────────────────────────────
Write-Host "Installing dependencies from requirements.txt..."
pip install -r requirements.txt --quiet
Write-Host "Dependencies installed." -ForegroundColor Green

# ── Create .env from template ──────────────────────────────────────────────────
if (Test-Path ".env") {
    Write-Host ".env already exists — skipping." -ForegroundColor Yellow
} else {
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host ".env file created from template." -ForegroundColor Green
    Write-Host ""
    Write-Host "ACTION REQUIRED: Open .env and fill in your values:" -ForegroundColor Yellow
    Write-Host "  AZURE_SUBSCRIPTION_ID  — your Azure subscription ID" -ForegroundColor Yellow
    Write-Host "  AZURE_RESOURCE_GROUP   — resource group containing the ADF factory" -ForegroundColor Yellow
    Write-Host "  AZURE_FACTORY_NAME     — ADF factory name" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Ask your team lead if you don't have these values." -ForegroundColor Yellow
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup complete!                       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Fill in .env with the three factory values (if not done yet)"
Write-Host "  2. Open this folder in VS Code:  code ."
Write-Host "  3. Open Copilot Chat and start using ADF tools"
Write-Host "  4. Sign in with your Entra ID account when the browser opens on first use"
Write-Host ""
