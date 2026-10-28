import test from 'node:test';
import assert from 'node:assert/strict';
import {PGlite} from '@electric-sql/pglite';
import {initDatabase} from '../database.js';
import {PgStore,UI,revision,createGate} from '../privacy/node.js';

// In-memory PostgreSQL WASM only. Never reads DATABASE_URL or uses network.
test('PostgreSQL schema, privacy events, retention and durable deletion gate',async()=>{
 const db=new PGlite();
 const query=async(sql,params=[])=>{const r=await db.query(sql,params);return {...r,rowCount:r.rows.length||r.affectedRows||0};};
 const pool={query,connect:async()=>({query,release(){}})};
 try{
  await initDatabase(pool);
  const store=new PgStore(pool);await store.init();await store.init();
  const fields=['controller','controller_address','contact','purposes','legal_basis','retention','recipients','transfers','rights','complaint','provision','automated','ai_use'];
  const p={version:'test',core_legal_basis:'art6_1_b',audit_retention_days:30,application_retention_days:7,notices:Object.fromEntries(Object.keys(UI).map(l=>[l,{...Object.fromEntries(fields.map(k=>[k,'TEST ONLY'])),policy_url:'https://example.invalid/privacy'}]))};
  assert.equal(await store.allowed(42,p),false);
  await store.record(42,'acknowledged','pl',p);assert.equal(await store.allowed(42,p),true);
  const audit=(await query('SELECT * FROM ewu_privacy_events')).rows[0];
  assert.equal(audit.version,'test');assert.equal(audit.revision,revision(p));assert.ok(audit.at);
  await query("INSERT INTO ewu_sessions(telegram_id,mode,data) VALUES(42,'candidate','{\"phone\":\"TEST\"}')");
  await store.record(42,'withdrawn','uk',p);assert.equal(await store.allowed(42,p),false);
  assert.equal((await query('SELECT * FROM ewu_sessions')).rows.length,0);
  await store.record(42,'deletion_requested','uz',p);await store.record(42,'acknowledged','uk',p);
  assert.equal(await store.allowed(42,p),false);
  assert.equal((await query('SELECT status FROM ewu_deletion_requests')).rows[0].status,'pending');
  // Pending rights requests outlive audit TTL and remain actionable by an operator.
  await query("UPDATE ewu_privacy_events SET at=now()-interval '31 days'");
  await query("INSERT INTO ewu_messages(id,telegram_id,direction,body,created_at) VALUES('00000000-0000-0000-0000-000000000001',42,'in','TEST',now()-interval '8 days')");
  await store.purge(p);
  assert.equal((await query('SELECT * FROM ewu_privacy_events')).rows.length,0);
  assert.equal((await query('SELECT * FROM ewu_messages')).rows.length,0);
  assert.equal((await query('SELECT * FROM ewu_deletion_requests')).rows.length,1);
  await store.record(43,'acknowledged','ru',p);assert.equal(await store.allowed(43,p),true);
  const updated=structuredClone(p);updated.notices.uk.contact='changed';assert.equal(await store.allowed(43,updated),false);
  // Real store + transport spy: no application rows from a pre-onboarding message.
  let continued=0;const messages=[];
  const gate=createGate({store,tg:async(_,body)=>messages.push(body),getPolicy:()=>p,onContinue:async()=>continued++});
  assert.equal(await gate({from:{id:44},chat:{id:44,type:'private'},text:'PRIVATE TEXT'}),true);
  assert.equal(continued,0);assert.equal(messages.length,Object.keys(UI).length);
  assert.equal((await query('SELECT * FROM ewu_applications')).rows.length,0);
 }finally{await db.close();}
});

test('EWU v2 additive migration, immutable evidence and non-destructive rollback',async()=>{
 const {readFile}=await import('node:fs/promises');
 const db=new PGlite();
 try{
  await db.exec(await readFile(new URL('../migrations/001_recruitment.up.sql',import.meta.url),'utf8'));
  await db.exec(await readFile(new URL('../migrations/001_recruitment.guard.sql',import.meta.url),'utf8'));
  await db.query("INSERT INTO ewu2_schema_version VALUES(1,'synthetic')");
  await db.query("INSERT INTO ewu2_privacy_records VALUES('p','test-user','v','hash','en','notice','acknowledged','test','SYNTHETIC','2026-10-28T00:00:00Z','','digest')");
  await assert.rejects(db.query("UPDATE ewu2_privacy_records SET decision='other'"));
  await assert.rejects(db.query('DELETE FROM ewu2_privacy_records'));
  await db.exec(await readFile(new URL('../migrations/001_recruitment.rollback.sql',import.meta.url),'utf8'));
  assert.equal((await db.query('SELECT * FROM ewu2_privacy_records')).rows.length,1);
  // A candidate owns multiple applications; partner/external vacancy identity is composite.
  await db.query("INSERT INTO ewu2_candidates(id,telegram_id,language,profile,created_at,updated_at) VALUES('c','synthetic','en','{}','test','test')");
  await assert.rejects(db.query("INSERT INTO ewu2_candidates(id,telegram_id,language,profile,created_at,updated_at) VALUES('c2','synthetic','en','{}','test','test')"));
  assert.equal((await db.query("SELECT count(*)::int AS n FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'ewu2_%'")).rows[0].n,26);
  await db.exec('CREATE ROLE ewu2_runtime NOLOGIN');
  await db.exec(await readFile(new URL('../migrations/002_runtime_permissions.sql',import.meta.url),'utf8'));
  await db.exec('SET ROLE ewu2_runtime');
  assert.equal((await db.query('SELECT count(*)::int AS n FROM ewu2_privacy_records')).rows[0].n,1);
  await assert.rejects(db.query('DELETE FROM ewu2_privacy_records'));
  await assert.rejects(db.query('DROP TABLE ewu2_audit_events'));
  await db.exec('RESET ROLE');
 }finally{await db.close();}
});

test('Full Python recruitment scenario SQL replay on PostgreSQL engine',async()=>{
 const {spawnSync}=await import('node:child_process');
 const {readFile}=await import('node:fs/promises');
 const python=process.env.EWU_TEST_PYTHON||'python3';
 const run=spawnSync(python,['tests/export_recruitment_trace.py'],{encoding:'utf8',maxBuffer:4*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 assert.equal(run.status,0,run.stderr);
 const trace=JSON.parse(run.stdout);
 const db=new PGlite();
 try{
  await db.exec(await readFile(new URL('../migrations/001_recruitment.up.sql',import.meta.url),'utf8'));
  await db.exec(await readFile(new URL('../migrations/001_recruitment.guard.sql',import.meta.url),'utf8'));
  for(let [sql,params] of trace){
   if(sql==='BEGIN IMMEDIATE')sql='BEGIN';
   let index=0;sql=sql.replaceAll('?',()=>`$${++index}`);
   await db.query(sql,params);
  }
  assert.equal((await db.query('SELECT status FROM ewu2_applications')).rows[0].status,'STARTED_WORK');
  assert.equal((await db.query('SELECT count(*)::int AS n FROM ewu2_candidates')).rows[0].n,1);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM ewu2_employment_starts')).rows[0].n,1);
  assert.equal((await db.query('SELECT amount_minor,payment_status FROM ewu2_commissions')).rows[0].payment_status,'UNPAID');
 }finally{await db.close();}
});
