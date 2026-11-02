// EWU CRM bridge v2. Script Properties: SHEET_ID, EWU_SHARED_SECRET.
// Do not deploy anonymously until authentication and the configured recipient
// have been reviewed. Never log request bodies, signatures or candidate fields.
const EWU_HEADERS = ['application_id','revision','kind','status','name','phone','city','profession','created_at','policy_revision','future_recruitment_consent','synced_at','payload_hash','event_id'];
function ewuHex_(bytes) {return bytes.map(v=>(v+256)%256).map(v=>('0'+v.toString(16)).slice(-2)).join('');}
function ewuMac_(value,key) {return ewuHex_(Utilities.computeHmacSha256Signature(value,key,Utilities.Charset.UTF_8));}
function ewuEqual_(a,b) {if(typeof a!=='string'||typeof b!=='string'||a.length!==b.length)return false;let n=0;for(let i=0;i<a.length;i++)n|=a.charCodeAt(i)^b.charCodeAt(i);return n===0;}
function ewuText_(value) {const s=String(value ?? '');return /^[\s]*[=+\-@]/.test(s)?"'"+s:s;}
function ewuSheet_(book,name,headers) {
 const sheet=book.getSheetByName(name);if(!sheet)throw Error('schema_missing');
 const got=sheet.getRange(1,1,1,headers.length).getValues()[0];
 if(JSON.stringify(got)!==JSON.stringify(headers))throw Error('schema_mismatch');return sheet;
}
function ewuBody_(data) {return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);}
function doPost(e) {
 let lock;
 try {
  const props=PropertiesService.getScriptProperties();const secret=props.getProperty('EWU_SHARED_SECRET');const sheetId=props.getProperty('SHEET_ID');
  if(!secret||secret.length<32||!sheetId)throw Error('configuration_missing');
  const raw=e?.postData?.contents;if(typeof raw!=='string'||raw.length>16000)throw Error('invalid_body');
  const envelope=JSON.parse(raw);if(typeof envelope.payload!=='string'||typeof envelope.timestamp!=='string'||!/^[0-9]{10}$/.test(envelope.timestamp)||Math.abs(Date.now()/1000-Number(envelope.timestamp))>300)throw Error('invalid_timestamp');
  if(!ewuEqual_(ewuMac_(envelope.timestamp+'.'+envelope.payload,secret),envelope.signature))throw Error('authentication_failed');
  const p=JSON.parse(envelope.payload);const keys=['event_id','application_id','revision','kind','status','name','phone','city','profession','created_at','policy_revision','future_recruitment_consent'];
  if(JSON.stringify(Object.keys(p).sort())!==JSON.stringify(keys.sort())||!Number.isSafeInteger(p.revision)||p.revision<1||p.future_recruitment_consent!==false)throw Error('invalid_schema');
  if(!/^[0-9a-f-]{36}$/.test(p.event_id)||!/^[0-9a-f-]{36}$/.test(p.application_id)||!['candidate','employer','legal'].includes(p.kind)||!['NEW','CONTACTED','OFFERED','CONFIRMED','TRAVEL_PLANNED','ARRIVED','STARTED','CLOSED','WITHDRAWN'].includes(p.status))throw Error('invalid_identity');
  for(const k of keys.filter(k=>!['revision','future_recruitment_consent'].includes(k)))if(typeof p[k]!=='string'||p[k].length>1000)throw Error('invalid_value');
  lock=LockService.getScriptLock();lock.waitLock(10000);
  const book=SpreadsheetApp.openById(sheetId);
  const candidates=ewuSheet_(book,'EWU_Candidates',EWU_HEADERS);
  const sync=ewuSheet_(book,'EWU_Sync',['event_id','payload_hash','synced_at']);
  const history=ewuSheet_(book,'EWU_History',['application_id','revision','status','changed_at','event_id']);
  const hash=ewuHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,envelope.payload,Utilities.Charset.UTF_8));
  const synced=sync.getLastRow()>1?sync.getRange(2,1,sync.getLastRow()-1,2).getValues():[];
  const prior=synced.find(row=>row[0]===p.event_id);if(prior&&prior[1]!==hash)throw Error('event_conflict');
  if(!prior){
   const rows=candidates.getLastRow()>1?candidates.getRange(2,1,candidates.getLastRow()-1,EWU_HEADERS.length).getValues():[];
   const index=rows.findIndex(row=>row[0]===p.application_id);const old=index>=0?rows[index]:null;
   if(old&&Number(old[1])===p.revision&&old[12]!==hash)throw Error('revision_conflict');
   const now=new Date().toISOString();
   if(!old||Number(old[1])<p.revision){
    const values=[p.application_id,p.revision,p.kind,p.status,p.name,p.phone,p.city,p.profession,p.created_at,p.policy_revision,false,now,hash,p.event_id];
    candidates.getRange(index>=0?index+2:candidates.getLastRow()+1,1,1,values.length).setValues([values.map(v=>typeof v==='string'?ewuText_(v):v)]);
   }
   // Recover a previous partial write without duplicating the status history.
   const historyIds=history.getLastRow()>1?history.getRange(2,5,history.getLastRow()-1,1).getValues().flat():[];
   if(!historyIds.includes(p.event_id))history.appendRow([p.application_id,p.revision,p.status,now,p.event_id]);
   sync.appendRow([p.event_id,hash,now]);SpreadsheetApp.flush();
  }
  const ack={event_id:p.event_id,ok:true,revision:p.revision,sheet_id:sheetId};
  const signature=ewuMac_(JSON.stringify(ack),secret);return ewuBody_({...ack,signature});
 }catch(error){return ewuBody_({ok:false,error:'request_rejected'});}
 finally{if(lock)lock.releaseLock();}
}

// Run once as the spreadsheet owner. Existing unrelated sheets are preserved.
function setupEWUSheets() {
 const props=PropertiesService.getScriptProperties();const id=props.getProperty('SHEET_ID');if(!id)throw Error('SHEET_ID missing');
 const book=SpreadsheetApp.openById(id);
 const schema={EWU_Candidates:EWU_HEADERS,EWU_History:['application_id','revision','status','changed_at','event_id'],EWU_Sync:['event_id','payload_hash','synced_at']};
 for(const [name,headers] of Object.entries(schema)){
  let sheet=book.getSheetByName(name);
  if(sheet){ewuSheet_(book,name,headers);continue;}
  sheet=book.insertSheet(name);sheet.getRange(1,1,1,headers.length).setValues([headers]);
  sheet.setFrozenRows(1);sheet.setHiddenGridlines(true);sheet.setColumnWidths(1,headers.length,190);
  sheet.getRange(1,1,1,headers.length).setBackground('#ebefed').setFontWeight('bold').setWrap(true);sheet.setRowHeight(1,48);
  sheet.getRange(1,1,Math.max(sheet.getMaxRows(),2),headers.length).createFilter();
 }
 SpreadsheetApp.flush();
}
