import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { bridgeText, createMosthrBridge, createMosthrClient } from '../mosthr-bridge.js';

const key='test-only-secret-'.repeat(4);
function fixture() {
  let jobs=[{ id:randomUUID(), title:'Test offer', city:'Płock', salaryRange:'30 PLN', description:'Test duties', agencyName:'Agency A', privacyUrl:'https://example.test/privacy', consentVersion:'a'.repeat(64) }];
  const state=new Map(), rows=[], sent=[], calls=[];
  let submitError=null, stage='new', deliveryFailure=false;
  const store={get:async id=>structuredClone(state.get(id)), put:async(id,s)=>state.set(id,structuredClone(s)), clear:async id=>state.delete(id),
    enqueue:async r=>{const old=rows.find(x=>x.publication_id===r.publicationId&&x.telegram_id===r.telegramId); if(old)return old; const row={id:r.id,publication_id:r.publicationId,telegram_id:r.telegramId,language:r.language,title:r.title,external_candidate_key:r.externalCandidateKey,payload:r.payload,state:'pending',attempts:0};rows.push(row);return row;},
    cleanup:async()=>{}, list:async id=>rows.filter(r=>r.telegram_id===id),
    work:async fn=>{for(const r of rows.filter(x=>['pending','delivered'].includes(x.state))){const next=await fn(r);Object.assign(r,next,{remote_id:next.remoteId||r.remote_id,last_stage:next.lastStage||r.last_stage,attempts:r.attempts+1});}}
  };
  const client={jobs:async()=>jobs, submit:async payload=>{calls.push(structuredClone(payload));if(submitError)throw submitError;return {applicationId:payload.applicationId,stage};},status:async(id,k)=>({applicationId:id,stage})};
  const bridge=createMosthrBridge({client,store,botUsername:'EWU_TestBot',subjectSecret:key,
    send:async(id,text)=>{if(deliveryFailure)throw new Error('Telegram unavailable');sent.push({id,text});}});
  const msg=(text,id=123,type='private',lang='uk')=>({from:{id,language_code:lang},chat:{id,type},text});
  const apply=async(id=123)=>{for(const s of [`/start mhr_${jobs[0].id}`,'/agree','Test Person','+48123456789','Płock','Warehouse','/now'])await bridge.handle(msg(s,id));};
  return {bridge,msg,apply,state,rows,sent,calls,get job(){return jobs[0];},set jobs(v){jobs=v;},set stage(v){stage=v;},set submitError(v){submitError=v;},set deliveryFailure(v){deliveryFailure=v;}};
}
test('all seven languages explain recipient, privacy notice and explicit consent',()=>{
  for(const lang of ['uk','pl','ru','en','es','pt','de']) {const t=bridgeText[lang];assert.ok(t.consent);assert.ok(t.policy);assert.match(t.fields,/\/agree/);assert.match(t.fields,/\/cancel/);assert.equal(t.questions.length,4);}
});
test('HTTPS and sufficiently long secrets are mandatory; redirects cannot receive credentials',async()=>{
  assert.throws(()=>createMosthrClient({baseUrl:'http://example.test',key}));
  assert.throws(()=>createMosthrClient({baseUrl:'https://user:pass@example.test',key}));
  assert.throws(()=>createMosthrClient({baseUrl:'https://example.test',key:'short'}));
  let options;
  const client=createMosthrClient({baseUrl:'https://example.test',key,fetchImpl:async(url,o)=>{options=o;return {ok:true,json:async()=>({jobs:[]})};}});
  await client.jobs();assert.equal(options.redirect,'error');assert.equal(options.headers.Authorization,`Bearer ${key}`);
});
test('legacy messages and group messages are not captured',async()=>{
  const f=fixture();assert.equal(await f.bridge.handle(f.msg('hello')),false);
  assert.equal(await f.bridge.handle(f.msg('/jobs',123,'group')),false);
  assert.equal(f.sent.length,0);
});
test('consent is required before collecting a name, cancellation removes the form',async()=>{
  const f=fixture();await f.bridge.handle(f.msg(`/start mhr_${f.job.id}`));
  await f.bridge.handle(f.msg('Private Name Before Consent'));
  assert.deepEqual(f.state.get(123).data,{});assert.equal(f.rows.length,0);
  await f.bridge.handle(f.msg('/cancel'));assert.equal(f.state.has(123),false);
  assert.equal(await f.bridge.handle(f.msg('legacy message')),false);
});
test('long descriptions cannot truncate recipient or consent instructions',async()=>{
  const f=fixture();f.job.description='x'.repeat(5000);
  await f.bridge.handle(f.msg(`/start mhr_${f.job.id}`));
  assert.match(f.sent.at(-1).text,/Agency A/);assert.match(f.sent.at(-1).text,/https:\/\/example.test\/privacy/);assert.match(f.sent.at(-1).text,/\/agree/);
  assert.ok(f.sent.every(m=>m.text.length<=4096));
});
test('expired forms remain outside legacy AI until reset or a new application',async()=>{
  const f=fixture();f.state.set(123,{step:'expired',language:'uk'});
  assert.equal(await f.bridge.handle(f.msg('Late private answer')),true);
  assert.equal(f.rows.length,0);assert.match(f.sent.at(-1).text,/недоступна/);
  assert.equal(await f.bridge.handle(f.msg('/start')),false);assert.equal(f.state.has(123),false);
});
test('changed publication or closed job cannot be submitted with stale consent',async()=>{
  const f=fixture();await f.bridge.handle(f.msg(`/start mhr_${f.job.id}`));
  for(const s of ['/agree','Test Person','+48123456789','Płock','Warehouse'])await f.bridge.handle(f.msg(s));
  f.job.consentVersion='b'.repeat(64);await f.bridge.handle(f.msg('/now'));
  assert.equal(f.rows.length,0);assert.equal(f.state.has(123),false);
});
test('queue retries retain the same identity, purge delivered PII and notify only on stage change',async()=>{
  const f=fixture();await f.apply();f.submitError=new Error('Offline');
  const id=f.rows[0].payload.applicationId;
  await f.bridge.tick();assert.equal(f.rows[0].state,'pending');assert.equal(f.rows[0].payload.candidate.fullName,'Test Person');
  f.submitError=null;await f.bridge.tick();assert.equal(f.rows[0].state,'delivered');assert.deepEqual(f.rows[0].payload,{});
  assert.equal(f.calls[0].applicationId,id);assert.equal(f.calls[1].applicationId,id);
  f.stage='interview';await f.bridge.tick();assert.match(f.sent.at(-1).text,/Етап співбесіди/);
  const n=f.sent.length;await f.bridge.tick();assert.equal(f.sent.length,n);
  f.stage='withdrawn';await f.bridge.tick();assert.equal(f.rows[0].state,'finished');
});
test('rejected delivery purges PII; temporary Telegram outage does not mark delivered',async()=>{
  const f=fixture();await f.apply();f.submitError=Object.assign(new Error('Conflict'),{status:409});await f.bridge.tick();
  assert.equal(f.rows[0].state,'blocked');assert.deepEqual(f.rows[0].payload,{});
  const g=fixture();await g.apply();g.deliveryFailure=true;await g.bridge.tick();assert.equal(g.rows[0].state,'pending');assert.ok(g.rows[0].payload.candidate);
});
test('different candidates have distinct pseudonyms; status lists are private',async()=>{
  const f=fixture();await f.apply(123);await f.apply(456);
  assert.notEqual(f.rows[0].external_candidate_key,f.rows[1].external_candidate_key);
  assert.equal(f.rows[0].external_candidate_key.includes('123'),false);
  await f.bridge.handle(f.msg('/status',789));assert.equal(f.sent.at(-1).id,789);assert.match(f.sent.at(-1).text,/немає заявок/);
});
