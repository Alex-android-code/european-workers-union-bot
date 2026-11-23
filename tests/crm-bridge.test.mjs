import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';

const secret='synthetic-test-secret-'.repeat(3),sheetId='syntheticSheetId1234567890';
const mac=s=>crypto.createHmac('sha256',secret).update(s).digest('hex');
function context(){
 const sheets=new Map();let writeCount=0;
 class Sheet{
  constructor(){this.rows=[];}
  getLastRow(){return this.rows.length;}
  getMaxRows(){return 1000;}
  setFrozenRows(){return this;} setHiddenGridlines(){return this;} setColumnWidths(){return this;} setRowHeight(){return this;}
  appendRow(row){this.rows.push(row);writeCount++;}
  getRange(r,c,h,w){const self=this;return {
   getValues(){return Array.from({length:h},(_,i)=>Array.from({length:w},(_,j)=>self.rows[r-1+i]?.[c-1+j]??''));},
   setValues(values){for(let i=0;i<h;i++){self.rows[r-1+i]??=[];for(let j=0;j<w;j++)self.rows[r-1+i][c-1+j]=values[i][j];}writeCount++;return this;},
   setBackground(){return this;},setFontWeight(){return this;},setWrap(){return this;},createFilter(){return this;}
  };}
 }
 const book={getSheetByName:n=>sheets.get(n),insertSheet:n=>{const s=new Sheet();sheets.set(n,s);return s;}};
 const ctx=vm.createContext({Date,JSON,Math,Number,String,Error,Object,Array,
  PropertiesService:{getScriptProperties:()=>({getProperty:k=>({EWU_SHARED_SECRET:secret,SHEET_ID:sheetId}[k])})},
  Utilities:{Charset:{UTF_8:'UTF-8'},DigestAlgorithm:{SHA_256:'sha256'},computeHmacSha256Signature:(s,k)=>[...crypto.createHmac('sha256',k).update(s).digest()],computeDigest:(_,s)=>[...crypto.createHash('sha256').update(s).digest()]},
  SpreadsheetApp:{openById:id=>{assert.equal(id,sheetId);return book;},flush(){}},
  LockService:{getScriptLock:()=>({waitLock(){},releaseLock(){}})},
  ContentService:{MimeType:{JSON:'json'},createTextOutput:text=>({setMimeType:()=>text})},
 });
 vm.runInContext(fs.readFileSync(new URL('../crm/Code.gs',import.meta.url),'utf8'),ctx);
 ctx.setupEWUSheets();
 const payload={event_id:'11111111-1111-4111-8111-111111111111',application_id:'22222222-2222-4222-8222-222222222222',revision:1,kind:'candidate',status:'NEW',name:'=IMPORTXML("https://example.invalid")',phone:'+48123456789',city:'TEST CITY',profession:'TEST WORK',created_at:'2026-11-02',policy_revision:'test-policy',future_recruitment_consent:false};
 function post(p=payload,overrides={}){
  const text=JSON.stringify(p);const timestamp=String(Math.floor(Date.now()/1000));
  const envelope={timestamp,payload:text,signature:mac(timestamp+'.'+text),...overrides};
  return JSON.parse(ctx.doPost({postData:{contents:JSON.stringify(envelope)}}));
 }
 return {ctx,sheets,payload,post,writes:()=>writeCount};
}

test('signed request upserts one candidate, history and receipt; retry is idempotent',()=>{
 const x=context(),a=x.post();assert.equal(a.ok,true);
 const {signature,...body}=a;assert.equal(signature,mac(JSON.stringify(body)));
 x.post();assert.equal(x.sheets.get('EWU_Candidates').rows.length,2);
 assert.equal(x.sheets.get('EWU_History').rows.length,2);assert.equal(x.sheets.get('EWU_Sync').rows.length,2);
 const row=x.sheets.get('EWU_Candidates').rows[1];assert.equal(row[4].startsWith("'="),true);assert.equal(row[5].startsWith("'+"),true);assert.equal(row[10],false);
});
test('invalid signatures or stale timestamps never write candidate data',()=>{
 const x=context(),before=x.writes();assert.equal(x.post(x.payload,{signature:'bad'}).ok,false);
 assert.equal(x.post(x.payload,{timestamp:'1000000000'}).ok,false);assert.equal(x.writes(),before);
});
test('same event with changed data and same revision with a new event are rejected',()=>{
 const x=context();x.post();assert.equal(x.post({...x.payload,name:'changed'}).ok,false);
 assert.equal(x.post({...x.payload,event_id:'33333333-3333-4333-8333-333333333333',name:'changed'}).ok,false);
});
test('higher version updates while delayed older version cannot overwrite it',()=>{
 const x=context();x.post();x.post({...x.payload,event_id:'33333333-3333-4333-8333-333333333333',revision:3,status:'OFFERED'});
 x.post({...x.payload,event_id:'44444444-4444-4444-8444-444444444444',revision:2,status:'CONTACTED'});
 assert.equal(x.sheets.get('EWU_Candidates').rows[1][3],'OFFERED');
});
test('unknown fields, automatic future consent, invalid state and changed schema are refused',()=>{
 const x=context();assert.equal(x.post({...x.payload,document:'not allowed'}).ok,false);
 assert.equal(x.post({...x.payload,future_recruitment_consent:true}).ok,false);
 assert.equal(x.post({...x.payload,status:'AUTO_HIRED'}).ok,false);
 x.sheets.get('EWU_Candidates').rows[0][0]='wrong';assert.equal(x.post().ok,false);
});
