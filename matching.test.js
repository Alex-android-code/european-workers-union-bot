import test from 'node:test';
import assert from 'node:assert/strict';
import { matchOffer, recommendOffers } from './matching.js';

test('preserves separate partner contracts at same workplace', () => {
 const candidate={profession:'welder',experience:'MIG welding',current_location:'Płock'};
 const offers=[
  {id:'a',partner_id:'one',contract_id:'c1',workplace_id:'factory',required_skills:'MIG',location:'Płock'},
  {id:'b',partner_id:'two',contract_id:'c2',workplace_id:'factory',required_skills:'MIG',location:'Płock'}
 ];
 const results=recommendOffers(candidate,offers);
 assert.equal(results.length,2);
 assert.deepEqual(results.map(x=>x.contract_id),['c1','c2']);
 assert.ok(results.every(x=>x.human_review_required));
});
test('missing evidence is unknown rather than rejection',()=>{
 const result=matchOffer({}, {id:'x',required_skills:'forklift',work_authorization_required:true});
 assert.equal(result.status,'review');
 assert.ok(result.checks.every(x=>x.state==='unknown'));
});
test('inactive offer is not recommended',()=>{
 assert.deepEqual(recommendOffers({},[{id:'x',active:false}]),[]);
});
test('missing skill evidence requires review, not rejection',()=>{
 const result=matchOffer({profession:'packer'}, {id:'x',required_skills:'welding'});
 assert.equal(result.checks[0].state,'needs_review');
 assert.equal(result.human_review_required,true);
});
