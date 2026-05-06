#!/bin/bash
# Start Credit Agent (port 5023)
# KYC is now handled by the n8n-kyc deployment
set -e

echo "Starting Credit Agent on port 5023..."
exec python /app/credit_agent.py
