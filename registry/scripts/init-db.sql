-- Initialize database with required extensions

-- Enable pgvector extension for semantic search (if available)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Create test database for pytest
CREATE DATABASE registry_test;
GRANT ALL PRIVILEGES ON DATABASE registry_test TO registry;

-- Note: Initial seed data (guardrail profiles, etc.) is loaded via Flask migrations
-- or the seed command, not here, since tables are created by SQLAlchemy migrations.
