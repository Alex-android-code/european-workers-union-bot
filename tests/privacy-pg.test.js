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
  const fields=['controller','contact','purposes','legal_basis','retention','recipients','transfers','rights','complaint','provision','automated'];
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
  assert.equal(continued,0);assert.equal(messages.length,4);
  assert.equal((await query('SELECT * FROM ewu_applications')).rows.length,0);
 }finally{await db.close();}
});
