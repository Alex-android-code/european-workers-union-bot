import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../bot.js',import.meta.url),'utf8');
function runtime(){
 const sessions=new Map(),drafts=new Map(),applications=new Map(),deliveries=new Map(),settings=new Map(),requests=[],queries=[];
 let failSend=false;
 const pool={async query(sql,p=[]){
  queries.push(sql);
  if(sql.startsWith('SELECT * FROM ewu_sessions')) return {rows:sessions.has(p[0])?[sessions.get(p[0])]:[]};
  if(sql.startsWith('INSERT INTO ewu_sessions')){sessions.set(p[0],{lang:p[1],mode:p[2],step:p[3],data:JSON.parse(p[4]),last_message_id:p[5]??sessions.get(p[0])?.last_message_id});}
  if(sql.startsWith('INSERT INTO ewu_drafts')) drafts.set(p[0]+':'+p[1],{lang:p[2],step:p[3],data:JSON.parse(p[4])});
  if(sql.startsWith('SELECT * FROM ewu_drafts')) return {rows:drafts.has(p[0]+':'+p[1])?[drafts.get(p[0]+':'+p[1])]:[]};
  if(sql.startsWith('DELETE FROM ewu_drafts')){for(const key of drafts.keys())if(key.startsWith(p[0]+':')&&(!p[1]||key===p[0]+':'+p[1]))drafts.delete(key);}
  if(sql.startsWith('INSERT INTO ewu_applications')&&!applications.has(p[0]))applications.set(p[0],p);
  if(sql.startsWith('SELECT value FROM ewu_settings'))return {rows:settings.has(p[0])?[{value:settings.get(p[0])}]:[]};
  if(sql.startsWith('INSERT INTO ewu_settings'))settings.set(p[0],p[1]);
  if(sql.startsWith('INSERT INTO ewu_delivery')&&!deliveries.has(p[0]))deliveries.set(p[0],{application_id:p[0],chat_id:p[1],body:p[2],attempts:0});
  if(sql.startsWith('SELECT * FROM ewu_delivery'))return {rows:[...deliveries.values()].filter(x=>!x.delivered_at)};
  if(sql.startsWith('UPDATE ewu_delivery SET delivered'))deliveries.get(p[0]).delivered_at=true;
  if(sql.startsWith('UPDATE ewu_delivery SET attempts'))deliveries.get(p[0]).attempts++;
  return {rows:[]};
 }};
 pool.connect=async()=>({...pool,release(){},on(){}});
 const process={env:{TELEGRAM_TOKEN:'synthetic',DATABASE_URL:'synthetic',EWU_ADMIN_IDS:'100',EWU_GROUP_IDS:'-200'},exit(){throw Error('exit')}};
 const fetch=async(url,opts)=>{const body=JSON.parse(opts.body);requests.push({method:url.split('/').at(-1),body});if(failSend&&url.endsWith('sendMessage'))throw Error('synthetic failure');return {json:async()=>({ok:true,result:{}})};};
 const stripped=source.replace(/^import .*;\n/gm,'').slice(0,source.replace(/^import .*;\n/gm,'').indexOf('http.createServer'));
 const api=new Function('pg','crypto','process','fetch','generateText',stripped+';return {handle,start,finalize,flushDelivery,phoneOk,L,flows,send,START_ALLOWED,groupAuthorized,init};')({Pool:class{constructor(){return pool}}},crypto,process,fetch,()=>{throw Error('AI not used')});
 return {...api,sessions,drafts,applications,deliveries,settings,requests,queries,setFail(x){failSend=x}};
}
const msg=(text,id=1)=>({from:{id:100},chat:{id:100,type:'private'},message_id:id,text});
test('Polling is locked without explicit approval',()=>assert.equal(runtime().START_ALLOWED,false));
for(const lang of ['uk','pl','ru','en','de','es','pt'])test('Complete candidate and employer questionnaires: '+lang,async()=>{
 const r=runtime();
 let messageId=1;
 for(const mode of ['candidate','employer']){
  r.sessions.set(100,{lang,mode:'menu',step:0,data:{}});
  await r.handle(msg(r.L[lang][mode],messageId++));
  const fields=r.flows[mode].fields;
  for(let i=0;i<fields.length;i++)await r.handle(msg(fields[i]==='phone'?'+48123456789':'Synthetic answer '+i,messageId++));
  assert.equal(r.sessions.get(100).mode,'menu');
 }
 assert.equal(r.applications.size,2);
 assert.ok(r.queries.every(sql=>!sql.includes('INSERT INTO candidates')));
});
test('/start resumes the saved step without discarding data',async()=>{
 const r=runtime();r.sessions.set(100,{lang:'uk',mode:'candidate',step:3,data:{full_name:'Synthetic'}});
 await r.handle(msg('/start source_test'));assert.equal(r.sessions.get(100).step,3);assert.equal(r.sessions.get(100).data.full_name,'Synthetic');
 assert.equal(r.requests.at(-1).body.text,r.flows.candidate.q.uk[3]);
});
test('Switch to employer and back restores candidate draft',async()=>{
 const r=runtime();r.sessions.set(100,{lang:'pl',mode:'candidate',step:4,data:{phone:'+48123456789'}});
 await r.handle(msg(r.L.pl.employer));assert.equal(r.sessions.get(100).mode,'employer');
 await r.handle(msg(r.L.pl.candidate,2));assert.equal(r.sessions.get(100).step,4);assert.equal(r.sessions.get(100).data.phone,'+48123456789');
});
test('Reset requires confirmation',async()=>{
 const r=runtime();r.sessions.set(100,{lang:'en',mode:'candidate',step:2,data:{full_name:'Synthetic'}});
 await r.handle(msg('/reset'));assert.equal(r.sessions.get(100).step,2);
 await r.handle(msg('/confirm_reset',2));assert.equal(r.sessions.get(100).mode,'language');
});
test('Only approved owner and approved group can bind',async()=>{
 const r=runtime();const m={from:{id:999},chat:{id:-200,type:'supergroup'},text:'/bindgroup'};
 await r.handle(m);assert.equal(r.settings.size,0);
 await r.handle({...m,from:{id:100},chat:{id:-999,type:'supergroup'}});assert.equal(r.settings.size,0);
 await r.handle({...m,from:{id:100}});assert.equal(r.settings.get('recruitment_group_chat_id'),'-200');
});
test('User content is sent as plain text',async()=>{
 const r=runtime();await r.send(100,'<synthetic>& text');assert.equal(r.requests[0].body.text,'<synthetic>& text');assert.equal(r.requests[0].body.parse_mode,undefined);
});
test('Phone validation requires a bounded international number',()=>{
 const r=runtime();assert.ok(r.phoneOk('+48 123 456 789'));assert.ok(!r.phoneOk('call +48123456789 now'));assert.ok(!r.phoneOk('123456789'));assert.ok(!r.phoneOk('+000000000'));
});
test('Replay after a send failure does not advance a second field',async()=>{
 const r=runtime();r.sessions.set(100,{lang:'en',mode:'candidate',step:0,data:{}});r.setFail(true);
 await assert.rejects(r.handle(msg('Synthetic',10)));assert.equal(r.sessions.get(100).step,1);
 r.setFail(false);await r.handle(msg('Synthetic',10));assert.equal(r.sessions.get(100).step,1);assert.equal(r.sessions.get(100).data.phone,undefined);
});
test('Same final message creates one application and one queued notification',async()=>{
 const r=runtime();r.settings.set('recruitment_group_chat_id','-200');const s={lang:'en',mode:'candidate'};
 await r.finalize(msg('last',20),s,'candidate',{full_name:'Synthetic'});await r.finalize(msg('last',20),s,'candidate',{full_name:'Synthetic'});
 assert.equal(r.applications.size,1);assert.equal(r.deliveries.size,1);assert.equal([...r.applications.values()][0][7],'NEW');assert.equal([...r.applications.values()][0][8],null);
});
test('Group delivery survives transient failure',async()=>{
 const r=runtime();r.settings.set('recruitment_group_chat_id','-200');await r.finalize(msg('last',20),{lang:'en'},'employer',{company:'Synthetic'});
 r.setFail(true);await r.flushDelivery();assert.equal([...r.deliveries.values()][0].attempts,1);assert.ok(![...r.deliveries.values()][0].delivered_at);
 r.setFail(false);await r.flushDelivery();assert.ok([...r.deliveries.values()][0].delivered_at);
});
test('Contact request is queued for recruiter delivery',async()=>{
 const r=runtime();r.settings.set('recruitment_group_chat_id','-200');r.sessions.set(100,{lang:'en',mode:'contact',data:{}});await r.handle(msg('Synthetic request',30));assert.equal(r.deliveries.size,1);
});
test('Startup refuses an existing webhook without deleting it',async()=>{
 const stripped=source.replace(/^import .*;\n/gm,'');assert.ok(!stripped.includes("tg('deleteWebhook'"));
 const setup=source.slice(source.indexOf('async function setup(){'),source.indexOf('async function poll(){'));
 let initCalls=0;
 const setupFn=new Function('pool','crypto','TOKEN','tg','init','safeError','process',setup+';return setup;')({connect:async()=>({query:async()=>({rows:[{acquired:true}]}),on(){}})},crypto,'synthetic',async()=>({url:'https://synthetic.invalid'}),async()=>{initCalls++},()=>{},{});
 await assert.rejects(setupFn(),/Webhook configured/);assert.equal(initCalls,0);
});
