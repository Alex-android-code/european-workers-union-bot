import fs from 'node:fs';
import crypto from 'node:crypto';
export const UI=JSON.parse(fs.readFileSync(new URL('./ui.json',import.meta.url),'utf8'));
const fields=['controller','controller_address','contact','purposes','legal_basis','retention','recipients','transfers','rights','complaint','provision','automated','ai_use'];
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
export const revision=p=>crypto.createHash('sha256').update(JSON.stringify(canonical(p))).digest('hex').slice(0,24);
export function render(p,lang) {
 const ui=UI[lang],n=p.notices[lang];
 return [ui.title+' — '+p.version,...(p.effective_at?[ui.effective_at+': '+p.effective_at]:[]),...fields.map(k=>ui[k]+': '+n[k]),'Polityka prywatności: '+n.policy_url,ui.note].join('\n\n');
}
export function validate(p) {
 if(typeof p.version!=='string'||!p.version.trim()) throw Error('Missing version');
 if(!['art6_1_b','art6_1_c','art6_1_f'].includes(p.core_legal_basis)) throw Error('Core processing needs a reviewed non-consent basis');
 for(const key of ['audit_retention_days','application_retention_days']) if(!Number.isInteger(p[key])||p[key]<1||p[key]>3650) throw Error('Invalid retention');
 for(const lang of Object.keys(UI)) {
  const n=p.notices?.[lang];
  for(const k of [...fields,'policy_url']) if(typeof n?.[k]!=='string'||!n[k].trim()) throw Error('Incomplete notice');
  const url=new URL(n.policy_url);
  if(url.protocol!=='https:'||!url.hostname||url.username||url.password) throw Error('Invalid policy URL');
  if(render(p,lang).length>3900) throw Error('Notice too long');
 }
 return p;
}
export function loadPolicy(){return validate(JSON.parse(fs.readFileSync(process.env.PRIVACY_CONFIG_FILE,'utf8')));}
export class PgStore {
 constructor(pool){this.pool=pool;}
 async init(){
  await this.pool.query(`CREATE TABLE IF NOT EXISTS ewu_privacy_events(id bigserial primary key,user_id bigint not null,action text not null,revision text not null,version text not null,locale text not null,notice text not null,at timestamptz not null default now())`);
  await this.pool.query('CREATE INDEX IF NOT EXISTS ewu_privacy_user ON ewu_privacy_events(user_id,id)');
  await this.pool.query(`CREATE TABLE IF NOT EXISTS ewu_deletion_requests(user_id bigint primary key,requested_at timestamptz not null default now(),status text not null default 'pending')`);
 }
 async purge(p){
  await this.pool.query("DELETE FROM ewu_privacy_events WHERE at < now() - ($1::int * interval '1 day')",[p.audit_retention_days]);
  for(const [table,time] of [['ewu_applications','created_at'],['ewu_sessions','updated_at'],['ewu_messages','created_at']])
   await this.pool.query(`DELETE FROM ${table} WHERE ${time} < now() - ($1::int * interval '1 day')`,[p.application_retention_days]);
 }
 async allowed(id,p){
  const r=await this.pool.query('SELECT action,revision FROM ewu_privacy_events WHERE user_id=$1 ORDER BY id DESC LIMIT 1',[id]);
  const pending=await this.pool.query("SELECT 1 FROM ewu_deletion_requests WHERE user_id=$1 AND status='pending'",[id]);
  return !pending.rowCount&&r.rows[0]?.action==='acknowledged'&&r.rows[0]?.revision===revision(p);
 }
 async record(id,action,lang,p){
  if(!['acknowledged','declined','withdrawn','deletion_requested'].includes(action)) throw Error('Unknown privacy action');
  const c=await this.pool.connect();
  try{
   await c.query('BEGIN');
   await c.query('INSERT INTO ewu_privacy_events(user_id,action,revision,version,locale,notice) VALUES($1,$2,$3,$4,$5,$6)',[id,action,revision(p),p.version,lang,render(p,lang)]);
   await c.query('DELETE FROM ewu_sessions WHERE telegram_id=$1',[id]);
   if(action==='deletion_requested') await c.query('INSERT INTO ewu_deletion_requests(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING',[id]);
   await c.query('COMMIT');
  }catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
 }
}
export function createGate({store,tg,getPolicy=loadPolicy,onContinue}){
 async function notice(id,p){
  for(const lang of Object.keys(UI)){
   const ui=UI[lang];
   await tg('sendMessage',{chat_id:id,text:p?render(p,lang):ui.unavailable,disable_web_page_preview:true,
    reply_markup:p?{inline_keyboard:[[{text:ui.continue,callback_data:`p:${revision(p)}:${lang}:yes`},{text:ui.decline,callback_data:`p:${revision(p)}:${lang}:no`}]]}:{remove_keyboard:true}});
  }
 }
 return async function gate(msg,callback=null){
  if(msg.chat?.type!=='private'||!msg.from?.id||msg.from.is_bot) return true;
  let p;try{p=getPolicy();}catch{await notice(msg.chat.id,null);return true;}
  await store.purge(p);
  const id=msg.from.id,lang=Object.hasOwn(UI,msg.from.language_code)?msg.from.language_code:'uk';
  const command=String(msg.text||'').trim().split(/\s/)[0].split('@')[0];
  if(callback){
   if(callback.from.id!==msg.chat.id) return true;
   await tg('answerCallbackQuery',{callback_query_id:callback.id});
   const a=String(callback.data||'').split(':');
   if(a.length!==4||a[0]!=='p'||a[1]!==revision(p)||!Object.hasOwn(UI,a[2])||!['yes','no'].includes(a[3])){await notice(msg.chat.id,p);return true;}
   const action=a[3]==='yes'?'acknowledged':'declined';
   await store.record(id,action,a[2],p);
   if(action==='acknowledged'&&await store.allowed(id,p)) await onContinue(msg);
   else await tg('sendMessage',{chat_id:msg.chat.id,text:UI[a[2]].stopped,reply_markup:{remove_keyboard:true}});
   return true;
  }
  if(['/withdraw','/delete_data'].includes(command)){
   const deletion=command==='/delete_data';
   await store.record(id,deletion?'deletion_requested':'withdrawn',lang,p);
   await tg('sendMessage',{chat_id:msg.chat.id,text:deletion?UI[lang].deleted+p.notices[lang].contact:UI[lang].stopped,reply_markup:{remove_keyboard:true}});
   return true;
  }
  if(['/start','/reset','/privacy'].includes(command)||!await store.allowed(id,p)){await notice(msg.chat.id,p);return true;}
  return false;
 };
}
