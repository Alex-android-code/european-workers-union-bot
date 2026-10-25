import test from 'node:test';
import assert from 'node:assert/strict';
import { matchVacancies } from '../src/vacancy-matcher.js';
const candidate = {profession:'warehouse worker',current_location:'Łódź',work_priority:'Need housing'};
const base = {id:'v1',status:'approved',approved:true,employer_verified:true,valid_until:'2026-12-31',profession:'warehouse worker',location:'Łódź',housing_provided:true};
test('matches a verified current vacancy and explains reasons',()=>{
 const result=matchVacancies(candidate,[base],new Date('2026-10-25'));
 assert.equal(result.length,1);
 assert.ok(result[0].score>0);
 assert.equal(result[0].requiresHumanReview,true);
});
test('rejects unapproved, unverified, expired and no-housing offers',()=>{
 const offers=[{...base,id:'unapproved',approved:false},{...base,id:'unverified',employer_verified:false},{...base,id:'expired',valid_until:'2025-01-01'},{...base,id:'nohousing',housing_provided:false}];
 assert.deepEqual(matchVacancies(candidate,offers,new Date('2026-10-25')),[]);
});
test('does not use nationality or AI score as an eligibility gate',()=>{
 const result=matchVacancies({...candidate,citizenship:'example',ai_score:1},[base],new Date('2026-10-25'));
 assert.equal(result.length,1);
});
