// Install this extension beside Code.gs. The owner installs an on-edit trigger
// for ewuStatusEdit. Missing e.user identity always rejects, never assumes owner.
const EWU_COMMAND_HEADERS=['id','application_id','status','expected_revision','actor','state','result','at','google_actor'];
const EWU_COMMAND_STATUSES=['NEW','FORM_COMPLETED','UNDER_REVIEW','APPROVED','DEPARTURE_CONFIRMED','ARRIVED','STARTED','REJECTED','WITHDRAWN','NO_SHOW','DID_NOT_START','FINISHED'];

function ewuCommandRequest_(p,props,secret,sheetId){
 if(p.operation==='sync_operational')return ewuOperationalRequest_(p,props,secret,sheetId);
 if(props.getProperty('BIDIRECTIONAL_REVIEWED')!=='1')throw Error('commands_disabled');
 if(typeof p.request_id!=='string'||!/^[0-9a-f-]{36}$/.test(p.request_id))throw Error('invalid_request_id');
 const lock=LockService.getScriptLock();lock.waitLock(10000);
 try{
  const book=SpreadsheetApp.openById(sheetId);
  const queue=ewuSheet_(book,'_EWU Commands',EWU_COMMAND_HEADERS);
  const rows=queue.getLastRow()>1?queue.getRange(2,1,queue.getLastRow()-1,EWU_COMMAND_HEADERS.length).getValues():[];
  let result;
  if(p.operation==='pull_status_commands'){
   if(JSON.stringify(Object.keys(p).sort())!==JSON.stringify(['operation','request_id']))throw Error('invalid_fields');
   result=rows.filter(row=>row[5]==='pending').slice(0,20).map(row=>({id:String(row[0]),application_id:String(row[1]),status:String(row[2]),expected_revision:Number(row[3]),actor:String(row[4])}));
  }else if(p.operation==='ack_status_command'){
   if(!['applied','rejected'].includes(p.outcome)||typeof p.command_id!=='string')throw Error('invalid_ack');
   const index=rows.findIndex(row=>row[0]===p.command_id);if(index<0)throw Error('command_missing');
   const old=rows[index];
   if(old[5]!=='pending'&&old[5]!==p.outcome)throw Error('ack_conflict');
   queue.getRange(index+2,6,1,2).setValues([[p.outcome,ewuText_(JSON.stringify(p.result))]]);
   const apps=book.getSheetByName('Applications');
   if(apps&&apps.getLastRow()>1){
    const ids=apps.getRange(2,1,apps.getLastRow()-1,1).getValues().flat();const pos=ids.indexOf(old[1]);
    if(pos>=0){
     // Never overwrite a newer queued request's result.
     if(String(apps.getRange(pos+2,10).getValue())===p.command_id)apps.getRange(pos+2,11).setValue(p.outcome);
    }
   }
   result={ok:true};
  }else throw Error('unknown_operation');
  SpreadsheetApp.flush();
  // Canonical top-level key order matches Python sort_keys=True.
  const response={request_id:p.request_id,result:result,sheet_id:sheetId};
  return ewuBody_({...response,signature:ewuMac_(ewuCanonical_(response),secret)});
 }finally{lock.releaseLock();}
}

function ewuCanonical_(value){
 if(Array.isArray(value))return '['+value.map(ewuCanonical_).join(',')+']';
 if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+ewuCanonical_(value[k])).join(',')+'}';
 return JSON.stringify(value);
}

function ewuStatusEdit(e){
 if(!e||!e.range||e.range.getSheet().getName()!=='Applications'||e.range.getColumn()!==8||e.range.getRow()<2||e.range.getNumRows()!==1||e.range.getNumColumns()!==1)return;
 const props=PropertiesService.getScriptProperties();if(props.getProperty('BIDIRECTIONAL_REVIEWED')!=='1')return;
 const email=e.user&&typeof e.user.getEmail==='function'?e.user.getEmail().toLowerCase():'';
 if(!email)throw Error('editor_identity_unavailable');
 const book=e.source;if(book.getId()!==props.getProperty('SHEET_ID'))throw Error('wrong_spreadsheet');
 const lock=LockService.getScriptLock();lock.waitLock(10000);
 try{
  const coordinators=book.getSheetByName('Coordinators');if(!coordinators||coordinators.getLastRow()<2)throw Error('coordinator_missing');
  const list=coordinators.getRange(2,1,coordinators.getLastRow()-1,6).getValues();
  const matches=list.filter(row=>String(row[2]).toLowerCase()===email&&['OWNER','COORDINATOR'].includes(row[4])&&row[5]===true);
  if(matches.length!==1||! /^[1-9][0-9]{0,18}$/.test(String(matches[0][3])))throw Error('coordinator_not_authorized');
  const sheet=e.range.getSheet(),row=e.range.getRow();
  const fields=sheet.getRange(row,1,1,11).getValues()[0];
  const status=String(e.value||'');if(!EWU_COMMAND_STATUSES.includes(status)||fields[7]!==status)throw Error('invalid_status');
  if(! /^[0-9a-f-]{36}$/.test(String(fields[0]))||!Number.isSafeInteger(fields[6])||fields[6]<1)throw Error('invalid_application');
  const queue=ewuSheet_(book,'_EWU Commands',EWU_COMMAND_HEADERS);
  if(queue.getLastRow()>1&&queue.getRange(2,1,queue.getLastRow()-1,6).getValues().some(r=>r[1]===fields[0]&&r[5]==='pending'))throw Error('request_already_pending');
  const id=Utilities.getUuid();queue.appendRow([id,fields[0],status,fields[6],String(matches[0][3]),'pending','',new Date().toISOString(),email]);
  sheet.getRange(row,9,1,3).setValues([[fields[6],id,'pending']]);SpreadsheetApp.flush();
 }finally{lock.releaseLock();}
}

function setupEWUCommands(){
 const id=PropertiesService.getScriptProperties().getProperty('SHEET_ID');
 if(!id)throw Error('SHEET_ID missing');const book=SpreadsheetApp.openById(id);
 let sheet=book.getSheetByName('_EWU Commands');
 if(!sheet){sheet=book.insertSheet('_EWU Commands');sheet.getRange(1,1,1,EWU_COMMAND_HEADERS.length).setValues([EWU_COMMAND_HEADERS]);sheet.hideSheet();}
 ewuSheet_(book,'_EWU Commands',EWU_COMMAND_HEADERS);
 const protection=sheet.protect().setDescription('EWU command journal — owner only');
 protection.removeEditors(protection.getEditors());if(protection.canDomainEdit())protection.setDomainEdit(false);
}
