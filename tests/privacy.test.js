import test from 'node:test';
import assert from 'node:assert/strict';
import {UI,validate,revision,render,createGate,PgStore} from '../privacy/node.js';
function fixture(){
 const keys=['controller','contact','purposes','legal_basis','retention','recipients','transfers','rights','complaint','provision','automated'];
 return {version:'test-v1',core_legal_basis:'art6_1_b',audit_retention_days:30,application_retention_days:7,notices:Object.fromEntries(Object.keys(UI).map(lang=>[lang,{...Object.fromEntries(keys.map(k=>[k,'TEST ONLY '+k])),policy_url:'https://example.invalid/privacy'}]))};
}
function setup(){
 let policy=fixture();const sent=[],events=[],pending=new Set();let continued=0;
 const store={purge:async()=>{},record:async(id,action,lang,p)=>{events.push({id,action,lang,key:revision(p),notice:render(p,lang)});if(action==='deletion_requested')pending.add(id);},allowed:async(id,p)=>{const e=events.findLast(e=>e.id===id);return !pending.has(id)&&e?.action==='acknowledged'&&e.key===revision(p);}};
 const gate=createGate({store,getPolicy:()=>validate(policy),tg:async(method,body)=>sent.push({method,body}),onContinue:async()=>continued++});
 const msg=(text='/start',id=42)=>({text,from:{id,language_code:'uk'},chat:{id,type:'private'}});
 const click=async(action='yes',key=revision(policy),id=42)=>gate(msg('',id),{id:'cb',from:{id},data:`p:${key}:uk:${action}`});
 return {policy,sent,events,store,gate,msg,click,continued:()=>continued};
}
test('four notices, no intake before acknowledgement; positive flow',async()=>{
 const x=setup();assert.equal(await x.gate(x.msg('SECRET')),true);assert.equal(x.sent.length,4);assert.equal(x.events.length,0);
 assert.ok(!JSON.stringify(x.sent).includes('SECRET'));
 await x.click();assert.equal(x.continued(),1);assert.equal(await x.gate(x.msg('questionnaire')),false);
 assert.equal(x.events[0].action,'acknowledged');assert.equal(x.events[0].notice,render(x.policy,'uk'));
});
test('decline, withdrawal, deletion and user isolation',async()=>{
 const x=setup();await x.click('no');assert.equal(await x.gate(x.msg('intake')),true);
 await x.click();await x.gate(x.msg('/withdraw'));assert.equal(await x.store.allowed(42,x.policy),false);
 await x.click();await x.gate(x.msg('/delete_data'));await x.click();assert.equal(await x.store.allowed(42,x.policy),false);
 assert.equal(await x.store.allowed(43,x.policy),false);
});
test('policy text change, stale buttons, malformed callbacks',async()=>{
 const x=setup();const old=revision(x.policy);await x.click();x.policy.notices.pl.retention='CHANGED';
 assert.equal(await x.gate(x.msg('intake')),true);await x.click('yes',old);assert.equal(x.continued(),1);
 await x.click('unknown');assert.equal(x.continued(),1);await x.click();assert.equal(x.continued(),2);
});
test('missing legal data and group updates fail closed',async()=>{
 const x=setup();x.policy.notices.uz.contact='';await x.gate(x.msg());assert.ok(x.sent.every(s=>!s.body.reply_markup.inline_keyboard));
 x.sent.length=0;const m=x.msg();m.chat.type='group';assert.equal(await x.gate(m),true);assert.equal(x.sent.length,0);
});
test('URL, retention and notice size validated',()=>{
 for(const mutate of [p=>p.core_legal_basis='consent',p=>p.notices.uk.policy_url='http://example.invalid',p=>p.audit_retention_days=0,p=>p.notices.uk.controller='x'.repeat(4000)]){const p=fixture();mutate(p);assert.throws(()=>validate(p));}
});
test('PgStore writes snapshot and request transactionally with parameters',async()=>{
 const calls=[];let released=false;
 const client={query:async(...args)=>calls.push(args),release:()=>released=true};
 const store=new PgStore({connect:async()=>client});
 await store.record(42,'deletion_requested','uz',fixture());
 assert.equal(calls[0][0],'BEGIN');assert.equal(calls.at(-1)[0],'COMMIT');assert.ok(released);
 assert.deepEqual(calls[1][1].slice(0,2),[42,'deletion_requested']);assert.equal(calls[1][1][5],render(fixture(),'uz'));
 assert.ok(calls.some(c=>c[0].startsWith('DELETE FROM ewu_sessions')));
 assert.ok(calls.some(c=>c[0].startsWith('INSERT INTO ewu_deletion_requests')));
});
test('PgStore rolls back and never logs DB errors',async()=>{
 const calls=[];const client={query:async(sql)=>{calls.push(sql);if(sql.startsWith('INSERT'))throw Error('private');},release:()=>calls.push('release')};
 await assert.rejects(new PgStore({connect:async()=>client}).record(42,'acknowledged','uk',fixture()));
 assert.ok(calls.includes('ROLLBACK'));assert.equal(calls.at(-1),'release');
});
