-- n8n uses its own schema migrations; this file is a placeholder
-- for any custom DB setup needed later (e.g., audit tables).

-- Ensure the n8n user has the right privileges
GRANT ALL PRIVILEGES ON DATABASE n8n TO n8n_user;
