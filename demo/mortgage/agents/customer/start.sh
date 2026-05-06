#!/bin/bash
# Start Customer Agent (port 5020) and Auth Agent (port 5021)
set -e

echo "Starting Authentication Agent on port 5021..."
python /app/auth_agent.py &

echo "Starting Customer Agent on port 5020..."
python /app/customer_agent.py
