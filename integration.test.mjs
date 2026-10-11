import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import pg from 'pg';
import {createBot} from './bot-core.mjs';
import {DurableInbox,processUpdate,syncOne,applicationId} from './sync.mjs';
import {enqueue,deliverOne} from './delivery.mjs';
import {acquireIntakeLock} from './intake-lock.mjs';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ewu-complete-'));
const remote=process.env.EWU_TEST_SOCKET;
if(remote && !/^\/tmp\/ewu-restore-[a-zA-Z0-9-]+\/socket$/.test(remote))throw new Error('Only isolated test sockets allowed');
if(process.env.EWU_TEST_DATABASE && !/^ewu_integration[a-zA-Z0-9_]*$/.test(process.env.EWU_TEST_DATABASE))throw new Error('Isolated database name required');
let engine, pool;
async function start(){
 if(remote)pool=new pg.Pool({host:remote,port:55432,user:'postgres',database:process.env.EWU_TEST_DATABASE||'ewu_integration',connectionTimeoutMillis:1000,max:3});
 else {
  const {PGlite}=await import('@electric-sql/pglite');
  engine=new PGlite(path.join(dir,'postgres'));
  const query=async(sql,p=[])=>{const r=await engine.query(sql,p);return {...r,rowCount:r.affectedRows||r.rows.length}};
  pool={query,connect:async()=>({query,release(){}}),end:()=>engine.close()};
 }
}
const schema=`CREATE TABLE candidates(id uuid primary key,full_name text,phone text,citizenship text,city text,source text,status text,notes text,telegram_chat text);
CREATE TABLE ewu_sessions(telegram_id bigint primary key,lang text,mode text,step int default 0,data jsonb default '{}',updated_at timestamptz default now());
CREATE TABLE ewu_applications(id uuid primary key,kind text not null,telegram_id bigint not null,username text default '',language text default 'en',full_name text default '',phone text default '',status text default 'NEW',ai_score int,ai_summary text default '',data jsonb default '{}',created_at timestamptz default now());
CREATE TABLE ewu_messages(id uuid primary key,telegram_id bigint not null,direction text not null,body text not null,created_at timestamptz default now());
CREATE TABLE ewu_settings(key text primary key,value text not null,updated_at timestamptz default now());`;
const exec=async sql=>remote?pool.query(sql):engine.exec(sql);
const key=crypto.randomBytes(32), botId=123;
let inbox=new DurableInbox(path.join(dir,'intake'),key,botId);
let bot;
const update=(id,text,user=999)=>({update_id:id,message:{from:{id:user},chat:{id:user,type:'private'},text}});
async function apply(u){return processUpdate(pool,botId,u,(c,u)=>bot.apply(c,u,botId))}
async function drain(){for(const u of inbox.pending()){await apply(u);inbox.acknowledge(u.update_id)}}
const scalar=async sql=>(await pool.query(sql)).rows[0].n;
function configure(){bot=createBot({pool,enqueue})}

test('full bot: application, CRM, notifications, replay, DB outage and restart',async()=>{
 await start();await exec(schema);await exec(fs.readFileSync(new URL('./migration.sql',import.meta.url),'utf8'));
 await pool.query("INSERT INTO ewu_settings(key,value)VALUES('recruitment_group_chat_id','-100')");configure();
 const texts=['/start','🇬🇧 English','👷 I’m looking for work','SYNTHETIC EWU TEST','+48000000000','Test city','TEST','Welder','Ten years of synthetic experience','Test permit','Test rate','Test priority','12 months','B'];
 const updates=texts.map((s,i)=>update(i+1,s));
 inbox.ingest(updates);
 const unavailable={connect:async()=>{throw Object.assign(new Error('unavailable'),{code:'ECONNREFUSED'})}};
 await assert.rejects(processUpdate(unavailable,botId,updates[0],()=>{}));
 assert.equal(inbox.pending().length,updates.length);
 await pool.end();pool=null;
 if(remote && process.env.EWU_TEST_CLUSTER){
  execFileSync('runuser',['-u','postgres','--','pg_ctl','-D',process.env.EWU_TEST_CLUSTER,'stop','-m','fast'],{stdio:'ignore'});
  await start();
  await assert.rejects(pool.query('SELECT 1'));
  await pool.end();pool=null;
  execFileSync('runuser',['-u','postgres','--','pg_ctl','-D',process.env.EWU_TEST_CLUSTER,'-l',process.env.EWU_TEST_CLUSTER+'/test-restart.log','start'],{stdio:'ignore'});
 }
 // Actual durable DB engine close/reopen; intake object reconstructed independently.
 await start();configure();inbox=new DurableInbox(path.join(dir,'intake'),key,botId);
 await drain();
 assert.equal(Number(await scalar("SELECT count(*) AS n FROM ewu_applications WHERE kind='candidate'")),1);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM candidates')),0);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM ewu_sync_jobs WHERE completed_at IS NULL')),1);
 await syncOne(pool);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM candidates')),1);
 for(const u of updates)assert.equal(await apply(u),false);
 inbox.ingest(updates);await drain();await syncOne(pool);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM candidates')),1);
 const jobs=Number(await scalar('SELECT count(*) AS n FROM ewu_delivery_jobs'));
 const final=updates.at(-1);
 const notification=await pool.query('SELECT * FROM ewu_delivery_jobs WHERE update_id=$1 ORDER BY ordinal',[final.update_id]);
 assert.equal(notification.rows.length,2);assert.equal(String(notification.rows[0].chat_id),'-100');
 const sent=[];
 const telegram=async(method,body)=>{assert.equal(method,'sendMessage');sent.push(body);return {message_id:sent.length}};
 while(await deliverOne(pool,telegram)){}
 assert.equal(sent.length,jobs);assert.equal(sent.filter(x=>String(x.chat_id)==='-100').length,1);
 assert.equal(await deliverOne(pool,telegram),false);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM ewu_delivery_jobs WHERE sent_at IS NULL')),0);
 // A new application by the same person is valid and has a different identity.
 const another=update(200,'new application');
 await processUpdate(pool,botId,another,async c=>{
  await c.query('INSERT INTO ewu_applications(id,kind,telegram_id)VALUES($1,$2,$3)',[applicationId(botId,200,'candidate'),'candidate',999]);
 });
 await syncOne(pool);assert.equal(Number(await scalar('SELECT count(*) AS n FROM candidates')),2);
 await pool.end();
});

test('rollback, retry journal, per-chat ordering and replay preserve CRM edits',async()=>{
 await start();configure();
 await assert.rejects(processUpdate(pool,botId,update(300,'rollback'),async c=>{
  await c.query('INSERT INTO ewu_applications(id,kind,telegram_id)VALUES($1,$2,$3)',[applicationId(botId,300,'candidate'),'candidate',999]);
  await enqueue(c,botId,300,0,{chat_id:-100,text:'test'});throw new Error('force rollback');
 }));
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM ewu_processed_updates WHERE update_id=300')),0);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM ewu_delivery_jobs WHERE update_id=300')),0);
 assert.equal(Number(await scalar("SELECT count(*) AS n FROM ewu_applications WHERE id='"+applicationId(botId,300,'candidate')+"'")),0);
 await processUpdate(pool,botId,update(301,'retry'),async c=>{
  await c.query('INSERT INTO ewu_applications(id,kind,telegram_id)VALUES($1,$2,$3)',[applicationId(botId,301,'candidate'),'candidate',999]);
  await enqueue(c,botId,301,0,{chat_id:-100,text:'A'});await enqueue(c,botId,301,1,{chat_id:-100,text:'B'});
  await enqueue(c,botId,301,2,{chat_id:-200,text:'C'});
 });
 await exec("ALTER TABLE candidates ADD CONSTRAINT test_sync_failure CHECK (full_name!='EWU candidate') NOT VALID");
 await syncOne(pool,()=>.5);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM ewu_error_events WHERE component=\'candidate_sync\'')),1);
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM ewu_sync_jobs WHERE completed_at IS NULL')),1);
 await exec('ALTER TABLE candidates DROP CONSTRAINT test_sync_failure');
 await pool.query('UPDATE ewu_sync_jobs SET next_attempt_at=now() WHERE completed_at IS NULL');await syncOne(pool);
 let calls=0;const failing=async()=>{calls++;throw Object.assign(new Error('secret MUST NOT be logged'),{code:'TG_429',retryAfter:60})};
 await deliverOne(pool,failing,()=>.5);assert.equal(calls,1);
 const delivered=[];const ok=async(_,b)=>{delivered.push(b.text);return {message_id:500}};
 await deliverOne(pool,ok);assert.deepEqual(delivered,['C']);
 assert.equal(await deliverOne(pool,ok),false);
 const errors=await pool.query('SELECT error_code FROM ewu_error_events');assert.equal(errors.rows.some(x=>x.error_code.includes('secret')),false);
 await pool.query('UPDATE ewu_delivery_jobs SET next_attempt_at=now() WHERE sent_at IS NULL');
 while(await deliverOne(pool,ok)){};assert.deepEqual(delivered,['C','A','B']);
 await pool.query("UPDATE candidates SET status='CRM_EDITED',notes='MANUAL_NOTE'");
 await pool.query('UPDATE ewu_sync_jobs SET completed_at=NULL,next_attempt_at=now()');while(await syncOne(pool)){}
 assert.equal(Number(await scalar("SELECT count(*) AS n FROM candidates WHERE status='CRM_EDITED' AND notes='MANUAL_NOTE'")),3);
 await pool.end();
});

test('only one intake owner; crash releases kernel lock without deleting files',async()=>{
 const lockDir=path.join(dir,'lock');fs.mkdirSync(lockDir);
 const owner=await acquireIntakeLock(lockDir);
 await assert.rejects(acquireIntakeLock(lockDir),/unavailable/);
 await new Promise(r=>{owner.child.once('exit',r);owner.child.kill('SIGKILL')});
 const successor=await acquireIntakeLock(lockDir);
 await new Promise(r=>{successor.child.once('exit',r);successor.release()});
 assert.ok(fs.existsSync(path.join(lockDir,'intake.lock')));
});

test('historical backfill links records once and refuses ambiguous identity',async()=>{
 await start();
 const aid=applicationId(botId,600,'candidate'),cid=crypto.randomUUID();
 await pool.query("INSERT INTO ewu_applications(id,kind,telegram_id,full_name,phone)VALUES($1,'candidate',600,'SYNTHETIC HISTORY','+48000000001')",[aid]);
 await pool.query("INSERT INTO candidates(id,full_name,phone,source,telegram_chat,status,notes)VALUES($1,'SYNTHETIC HISTORY','+48000000001','EWU Telegram','600','HISTORICAL_STATUS','HISTORICAL_NOTE')",[cid]);
 await exec(fs.readFileSync(new URL('./backfill.sql',import.meta.url),'utf8'));
 await syncOne(pool);
 const historical=await pool.query('SELECT * FROM candidates WHERE id=$1',[cid]);
 assert.equal(historical.rows[0].ewu_application_id,aid);assert.equal(historical.rows[0].status,'HISTORICAL_STATUS');
 assert.equal(Number(await scalar("SELECT count(*) AS n FROM candidates WHERE full_name='SYNTHETIC HISTORY'")),1);
 const duplicateAid=applicationId(botId,601,'candidate');
 await pool.query("INSERT INTO ewu_applications(id,kind,telegram_id,full_name,phone)VALUES($1,'candidate',600,'SYNTHETIC HISTORY','+48000000001')",[duplicateAid]);
 await assert.rejects(exec(fs.readFileSync(new URL('./backfill.sql',import.meta.url),'utf8')),/Ambiguous/);
 await pool.query('ROLLBACK');
 assert.equal(Number(await scalar('SELECT count(*) AS n FROM candidates WHERE ewu_application_id=\''+duplicateAid+'\'')),0);
 await pool.end();
});

test('unconfigured preview refuses activation before Telegram requests',()=>{
 assert.throws(()=>execFileSync(process.execPath,[new URL('./bot.js',import.meta.url).pathname],{env:{...process.env,EWU_RUNTIME_ENABLED:'0',TELEGRAM_TOKEN:'SYNTHETIC',DATABASE_URL:'SYNTHETIC'},stdio:'pipe'}),e=>String(e.stderr).includes('Runtime activation requires reviewed rollout'));
});
