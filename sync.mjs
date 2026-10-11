// Durable encrypted intake and transactional candidate synchronization.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { journal } from './delivery.mjs';
function canonical(value) {
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 return JSON.stringify(value);
}
export function applicationId(botId, updateId, kind) {
 if(!/^[0-9]+$/.test(String(botId))||!Number.isSafeInteger(updateId)||updateId<0||!['candidate','employer','legal','contact'].includes(kind))throw new Error('Invalid application identity');
 const b=crypto.createHash('sha256').update('EWU/application/v1/'+botId+'/'+updateId+'/'+kind).digest().subarray(0,16);
 b[6]=(b[6]&15)|128;b[8]=(b[8]&63)|128;
 const h=b.toString('hex');return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);
}
export class DurableInbox {
 constructor(directory, key, botId) {
  if (!Buffer.isBuffer(key) || key.length !== 32) throw new Error('32-byte encryption key required');
  if (!/^[0-9]+$/.test(String(botId))) throw new Error('Invalid bot ID');
  this.directory = path.resolve(directory, String(botId)); this.key = key;
  fs.mkdirSync(this.directory, {recursive:true, mode:0o700});
 }
 syncDirectory() {const fd=fs.openSync(this.directory,'r');try{fs.fsyncSync(fd)}finally{fs.closeSync(fd)}}
 seal(data) {
  const iv=crypto.randomBytes(12), c=crypto.createCipheriv('aes-256-gcm',this.key,iv);
  const ciphertext=Buffer.concat([c.update(JSON.stringify(data),'utf8'),c.final()]);
  return Buffer.concat([iv,c.getAuthTag(),ciphertext]);
 }
 open(bytes) {
  const d=crypto.createDecipheriv('aes-256-gcm',this.key,bytes.subarray(0,12));
  d.setAuthTag(bytes.subarray(12,28));
  return JSON.parse(Buffer.concat([d.update(bytes.subarray(28)),d.final()]).toString('utf8'));
 }
 writeAtomic(name, bytes) {
  const target=path.join(this.directory,name), temporary=target+'.'+crypto.randomUUID()+'.tmp';
  const fd=fs.openSync(temporary,'wx',0o600);
  try{fs.writeFileSync(fd,bytes);fs.fsyncSync(fd)}finally{fs.closeSync(fd)}
  fs.renameSync(temporary,target);this.syncDirectory();
 }
 ingest(updates) {
  if(!Array.isArray(updates))throw new Error('Invalid batch');
  // Caller must keep one intake writer and serialize ingest calls.
  for(const update of updates) {
   const id=update.update_id;
   if(!Number.isSafeInteger(id)||id<0)throw new Error('Invalid update ID');
   const target=path.join(this.directory,id+'.event');
   if(fs.existsSync(target)) {
    const old=this.open(fs.readFileSync(target));
    if(canonical(old)!==canonical(update))throw new Error('Payload conflict for existing update ID');
   } else this.writeAtomic(id+'.event',this.seal(update));
  }
  // Only after the entire batch is durable may caller confirm Telegram's offset.
  const old=this.offset();
  const next=updates.reduce((v,u)=>Math.max(v,u.update_id+1),old);
  this.writeAtomic('offset',Buffer.from(String(next)));
  return next;
 }
 offset() {const p=path.join(this.directory,'offset'),n=fs.existsSync(p)?Number(fs.readFileSync(p,'utf8')):0;if(!Number.isSafeInteger(n)||n<0)throw new Error('Invalid durable offset');return n}
 pending() {
  return fs.readdirSync(this.directory).filter(n=>/^[0-9]+\.event$/.test(n))
   .filter(n=>!fs.existsSync(path.join(this.directory,n+'.ack')))
   .sort((a,b)=>Number(a.split('.')[0])-Number(b.split('.')[0]))
   .map(n=>this.open(fs.readFileSync(path.join(this.directory,n))));
 }
 acknowledge(id) {
  if(!Number.isSafeInteger(id)||!fs.existsSync(path.join(this.directory,id+'.event')))throw new Error('Unknown update');
  this.writeAtomic(id+'.event.ack',Buffer.from('committed'));
  // Retain the encrypted event as recovery history; do not delete it.
 }
}

export async function processUpdate(pool, botId, update, apply) {
 const c=await pool.connect();
 try {
  await c.query('BEGIN');
  // One ordered consumer per bot. This DB lock also prevents overlapping transactions.
  await c.query('SELECT pg_advisory_xact_lock($1::bigint)',[String(botId)]);
  const r=await c.query('INSERT INTO ewu_processed_updates(bot_id,update_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING update_id',[String(botId),update.update_id]);
  if(r.rowCount)await apply(c,update);
  await c.query('COMMIT');return !!r.rowCount;
 }catch(e){await c.query('ROLLBACK').catch(()=>{});throw e}
 finally{c.release()}
}

export const SYNC_CANDIDATE_SQL = `
 INSERT INTO candidates(id,ewu_application_id,full_name,phone,citizenship,city,source,status,notes,telegram_chat)
 SELECT a.id,a.id,COALESCE(NULLIF(a.full_name,''),'EWU candidate'),COALESCE(a.phone,''),
 COALESCE(a.data->>'citizenship',''),COALESCE(a.data->>'current_location',''),
 'EWU Telegram','Новий','EWU '||a.status||E'\\n'||COALESCE(a.ai_summary,''),a.telegram_id::text
 FROM ewu_applications a WHERE a.id=$1 AND a.kind='candidate'
 ON CONFLICT(ewu_application_id) DO NOTHING`;

export async function syncOne(pool, random=Math.random) {
 const c=await pool.connect();let applicationId;
 try {
  await c.query('BEGIN');
  const r=await c.query('SELECT application_id,attempts FROM ewu_sync_jobs WHERE completed_at IS NULL AND next_attempt_at<=now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1');
  if(!r.rowCount){await c.query('COMMIT');return false}
  applicationId=r.rows[0].application_id;
  await c.query('SAVEPOINT candidate_write');
  try {
   await c.query(SYNC_CANDIDATE_SQL,[applicationId]);
   const receipt=await c.query('SELECT id FROM candidates WHERE ewu_application_id=$1',[applicationId]);
   if(receipt.rowCount!==1)throw new Error('Candidate receipt missing');
   await c.query('UPDATE ewu_sync_jobs SET completed_at=now(),last_error_code=NULL,attempts=attempts+1 WHERE application_id=$1',[applicationId]);
  }catch(e){
   await c.query('ROLLBACK TO SAVEPOINT candidate_write');
   const attempts=r.rows[0].attempts+1;
   const delay=Math.min(3600,2**Math.min(attempts,11))*(0.5+random());
   // Only a bounded SQLSTATE is journalled, never exception text or candidate payload.
   const code=/^[0-9A-Z]{5}$/.test(e.code||'')?e.code:'UNKNOWN';
   await journal(c,'candidate_sync',applicationId,{code});
   await c.query("UPDATE ewu_sync_jobs SET attempts=attempts+1,next_attempt_at=now()+$2*interval '1 second',last_error_code=$3 WHERE application_id=$1",[applicationId,delay,code]);
  }
  await c.query('COMMIT');return true;
 }catch(e){await c.query('ROLLBACK').catch(()=>{});throw e}
 finally{c.release()}
}
