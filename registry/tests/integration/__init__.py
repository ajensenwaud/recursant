"""
Integration tests for the Recursant Agent Registry.

These tests require docker compose to be running with all services:
- api: Main Flask application
- db: PostgreSQL database
- redis: Redis cache
- test-agent: LangGraph-based test agent

Run with: make test-integration
"""
