-- Add selected_account_name column to integrations table
-- Run this SQL in your PostgreSQL database

ALTER TABLE integrations 
ADD COLUMN IF NOT EXISTS selected_account_name TEXT;

-- Verify the column was added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'integrations' 
AND column_name = 'selected_account_name';
