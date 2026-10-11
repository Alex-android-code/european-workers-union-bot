import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {DurableInbox,applicationId} from './sync.mjs';
test('application identity is stable and allows a later application from the same person',()=>{
 assert.equal(applicationId(123,10,'candidate'),applicationId(123,10,'candidate'));
 assert.notEqual(applicationId(123,10,'candidate'),applicationId(123,11,'candidate'));
 assert.notEqual(applicationId(123,10,'candidate'),applicationId(124,10,'candidate'));
 assert.notEqual(applicationId(123,10,'candidate'),applicationId(123,10,'employer'));
});
test('encrypted intake survives consumer failure, duplicate delivery and restart',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ewu-intake-')),key=crypto.randomBytes(32);
 let box=new DurableInbox(dir,key,123);
 const u={update_id:10,message:{text:'SYNTHETIC-CANDIDATE-PAYLOAD'}};
 assert.equal(box.ingest([u]),11);
 assert.equal(fs.readFileSync(path.join(dir,'123/10.event')).includes(Buffer.from(u.message.text)),false);
 const failedConsumer=async()=>{throw new Error('Database unavailable')};
 await assert.rejects(failedConsumer);
 box=new DurableInbox(dir,key,123);
 assert.deepEqual(box.pending(),[u]); assert.equal(box.offset(),11);
 box.ingest([u]);assert.equal(box.pending().length,1);
 box.ingest([{message:{text:'SYNTHETIC-CANDIDATE-PAYLOAD'},update_id:10}]);
 assert.equal(box.pending().length,1);
 box.acknowledge(10);box=new DurableInbox(dir,key,123);
 box.ingest([u]);assert.equal(box.pending().length,0);
 assert.ok(fs.existsSync(path.join(dir,'123/10.event')));
});
test('corruption and conflicting payload fail closed',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ewu-intake-')),key=crypto.randomBytes(32);
 const box=new DurableInbox(dir,key,456);box.ingest([{update_id:1,message:{text:'A'}}]);
 assert.throws(()=>box.ingest([{update_id:1,message:{text:'B'}}]),/Payload conflict/);
 const p=path.join(dir,'456/1.event'),b=fs.readFileSync(p);b[b.length-1]^=1;fs.writeFileSync(p,b);
 assert.throws(()=>box.pending());
});
test('partial batch failure does not confirm Telegram offset',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ewu-intake-')),key=crypto.randomBytes(32);
 const box=new DurableInbox(dir,key,789);
 const original=box.writeAtomic.bind(box);
 box.writeAtomic=(name,bytes)=>{if(name==='2.event')throw new Error('Disk full');return original(name,bytes)};
 assert.throws(()=>box.ingest([{update_id:1},{update_id:2}]),/Disk full/);
 assert.equal(box.offset(),0);assert.equal(box.pending().length,1);
 box.writeAtomic=original;box.ingest([{update_id:1},{update_id:2}]);
 assert.equal(box.offset(),3);assert.equal(box.pending().length,2);
});
