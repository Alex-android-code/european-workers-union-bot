import test from 'node:test';
import assert from 'node:assert/strict';
import {context} from './crm-bridge.test.mjs';

function setup(){
 const x=context();x.ctx.setupEWUOperational();
 const aid='22222222-2222-4222-8222-222222222222',cid='EWU-'+'a'.repeat(32);
 const p={operation:'sync_operational',request_id:'11111111-1111-4111-8111-111111111111',event_id:'33333333-3333-4333-8333-333333333333',application_id:aid,revision:1,
  candidate:[cid,'42','','=SYNTHETIC','','+48000000000','uk','','SYNTHETIC CITY','SYNTHETIC WORK','','','NEW','','2026-11-02','2026-11-02','v1','acknowledged','SQLite only',1],
  application:[aid,cid,'','NEW','2026-11-02','2026-11-02',1],
  history:[[aid+':1',aid,cid,'','NEW','2026-11-02','candidate','candidate',1]],
  privacy:[[cid+':privacy:1',cid,'42','v1','synthetic-revision','uk','2026-11-02','presented','2026-11-02','notice','synthetic']],requests:[]};
 return {...x,p,cid,aid};
}

test('operational projection populates requested tabs and repeats without duplicates',()=>{
 const x=setup();let response=x.post(x.p);assert.equal(response.result?.ok,true);
 assert.equal(x.post({...x.p,request_id:'44444444-4444-4444-8444-444444444444'}).result?.ok,true);
 for(const name of ['Candidates','Applications','Candidate Journey','RODO Register'])assert.equal(x.sheets.get(name).rows.length,2);
 assert.equal(x.sheets.get('Candidates').rows[1][3].startsWith("'="),true);
 assert.ok(x.sheets.has('Data Requests'));assert.ok(x.sheets.has('Dashboard'));
});

test('operational projection refuses field tampering, reassignment and stale overwrites',()=>{
 const x=setup();x.post(x.p);
 const changed=structuredClone(x.p);changed.candidate[3]='OTHER';assert.equal(x.post(changed).ok,false);
 const next=structuredClone(x.p);next.event_id='44444444-4444-4444-8444-444444444444';next.revision=2;next.application[6]=2;next.application[3]='FORM_COMPLETED';next.candidate[19]=2;
 assert.equal(x.post(next).result?.ok,true);
 const delayed=structuredClone(x.p);delayed.event_id='55555555-5555-4555-8555-555555555555';x.post(delayed);
 assert.equal(x.sheets.get('Applications').rows[1][3],'FORM_COMPLETED');
 const invalid=structuredClone(next);invalid.application[1]='EWU-'+'b'.repeat(32);assert.equal(x.post(invalid).ok,false);
});

test('signed command polling returns a bounded durable queue and idempotent acknowledgement',()=>{
 const x=setup();const commandId='66666666-6666-4666-8666-666666666666';
 x.sheets.get('_EWU Commands').appendRow([commandId,x.aid,'FORM_COMPLETED',1,'99','pending','','2026-11-02','owner@example.invalid']);
 const poll={operation:'pull_status_commands',request_id:x.p.request_id};
 const response=x.post(poll);assert.equal(response.result.length,1);assert.equal(response.result[0].actor,'99');
 const ack={operation:'ack_status_command',request_id:x.p.request_id,command_id:commandId,outcome:'applied',result:{revision:2}};
 assert.equal(x.post(ack).result.ok,true);assert.equal(x.post(ack).result.ok,true);assert.deepEqual(x.post(poll).result,[]);
 assert.equal(x.post({...ack,outcome:'rejected'}).ok,false);
});

test('command capture rejects absent editor identity and leaves queue empty',()=>{
 const x=setup();const event={range:{getSheet:()=>({getName:()=> 'Applications'}),getColumn:()=>8,getRow:()=>2,getNumRows:()=>1,getNumColumns:()=>1}};
 assert.throws(()=>x.ctx.ewuStatusEdit(event),/editor_identity_unavailable/);
 assert.equal(x.sheets.get('_EWU Commands').rows.length,1);
});
