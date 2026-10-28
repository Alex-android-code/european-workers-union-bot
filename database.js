export async function initDatabase(pool) {
 const ddl=[
  "CREATE TABLE IF NOT EXISTS ewu_sessions(telegram_id bigint primary key,lang text,mode text,step int default 0,data jsonb default '{}'::jsonb,updated_at timestamptz default now())",
  "CREATE TABLE IF NOT EXISTS ewu_applications(id uuid primary key,kind text not null,telegram_id bigint not null,username text default '',language text default 'en',full_name text default '',phone text default '',status text default 'NEW',ai_score int,ai_summary text default '',data jsonb default '{}'::jsonb,created_at timestamptz default now())",
  "CREATE TABLE IF NOT EXISTS ewu_messages(id uuid primary key,telegram_id bigint not null,direction text not null,body text not null,created_at timestamptz default now())",
  "CREATE TABLE IF NOT EXISTS ewu_settings(key text primary key,value text not null,updated_at timestamptz default now())"
 ];
 for(const s of ddl) await pool.query(s);
}
