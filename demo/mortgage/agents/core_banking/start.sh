#!/bin/bash
# Start Core Banking Agent (port 5024)
set -e

echo "Starting Core Banking Agent on port 5024..."
python /app/core_banking_agent.py
