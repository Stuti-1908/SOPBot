-- DadaAI Supabase schema — replaces the Airtable base used by
-- dashboard/ and payments/. Run this once against a new Supabase
-- project (SQL Editor -> paste -> Run), then put the project URL and
-- service_role key into dashboard/.env and payments/.env.

create table if not exists clients (
    id uuid primary key default gen_random_uuid(),
    client_name text not null default '',
    dashboard_token text unique not null,
    call_pin text not null default '',
    sop_pack_size integer not null default 0,
    sop_credits_used integer not null default 0,
    contact_email text not null default '',
    status text not null default 'Active',
    created_at timestamptz not null default now()
);

create table if not exists calls_log (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references clients(id),
    call_id text not null,
    process_name text not null default '',
    employee_name text not null default '',
    call_timestamp timestamptz not null default now(),
    sop_doc_url text not null default '',
    status text not null default 'Complete'
);

create table if not exists workflowiq_runs (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references clients(id),
    run_timestamp timestamptz not null default now(),
    process_names text not null default '',
    sops_analysed integer not null default 0,
    automation_opportunities_found integer not null default 0,
    pdf_filename text not null default '',
    report_type text not null default 'Single-SOP',
    -- "Pending" from the moment a WorkflowIQ product is purchased until staff
    -- runs the report and the tool marks it "Complete" (see workflowiq/app/ui.py).
    status text not null default 'Pending',
    contact_email text not null default '',
    payment_id text not null default ''
);

create index if not exists idx_clients_dashboard_token on clients(dashboard_token);
create index if not exists idx_calls_log_client_id on calls_log(client_id);
create index if not exists idx_workflowiq_runs_client_id on workflowiq_runs(client_id);
