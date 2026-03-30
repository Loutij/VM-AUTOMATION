-- Add completed_with_warnings to deployment status enum
-- Run this manually or via alembic
ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'completed_with_warnings' AFTER 'completed';
