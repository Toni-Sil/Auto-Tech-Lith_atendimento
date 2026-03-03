-- Migration: Add notification tracking to agendamentos
-- Antigravity Skill: database-migration

ALTER TABLE agendamentos 
ADD COLUMN IF NOT EXISTS confirm_status TEXT DEFAULT 'pending', -- pending, confirmed, rescheduled, no_show
ADD COLUMN IF NOT EXISTS notification_12h_sent BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS notification_6h_sent BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS notification_1h_sent BOOLEAN DEFAULT FALSE;

-- Index for faster querying of pending notifications
CREATE INDEX IF NOT EXISTS idx_agendamentos_notification_check 
ON agendamentos (data_hora, status, confirm_status);
