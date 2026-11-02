// Nine-tab projection. Run setupEWUOperational only against the new private CRM.
// It preserves unrelated tabs and fails on unexpected existing headers.
const EWU_OPERATIONAL_SCHEMA={
 Candidates:['Candidate ID','Telegram ID','Telegram username','First name','Last name','Phone','Language','Current country','City','Desired work','Vacancy ID','Available from','Status','Coordinator ID','Registered at','Updated at','Notice version','Acknowledgement','Private notes reference','Revision'],
 Applications:['Application ID','Candidate ID','Vacancy ID','Status','Created at','Updated at','Revision','Requested status','Expected revision','Request ID','Request result'],
 Vacancies:['Vacancy ID','Title','Country','City','Workplace address','Start date','Coordinator ID','Status','Verified at'],
 'Candidate Journey':['Event ID','Application ID','Candidate ID','From status','To status','Changed at','Source','Actor','Revision'],
 Coordinators:['Coordinator ID','Name','Google email','Telegram ID','Role','Active'],
 'RODO Register':['Event ID','Candidate ID','Telegram ID','Notice version','Notice revision','Language','Presented at','Action','Action at','Purpose','Legal basis'],
 'Data Requests':['Request ID','Candidate ID','Type','Requested at','Status','Assigned to','SQLite result','Sheets result','Other recipients result','Completed at'],
 Dashboard:['Показник','Значення'],Settings:['Setting','Value','Confirmation']
};
const EWU_RECEIPT_HEADERS=['event_id','application_id','revision','payload_hash','at'];

function ewuRows_(sheet,width){return sheet.getLastRow()>1?sheet.getRange(2,1,sheet.getLastRow()-1,width).getValues():[];}
function ewuPut_(sheet,row,width){
 const rows=ewuRows_(sheet,width),index=rows.findIndex(r=>String(r[0])===String(row[0]));
 sheet.getRange(index<0?sheet.getLastRow()+1:index+2,1,1,row.length).setValues([row.map(v=>typeof v==='string'?ewuText_(v):v)]);
}

function ewuOperationalRequest_(p,props,secret,sheetId){
 if(props.getProperty('OPERATIONAL_REVIEWED')!=='1')throw Error('operational_disabled');
 const keys=['operation','request_id','event_id','application_id','revision','candidate','application','history','privacy','requests'];
 if(JSON.stringify(Object.keys(p).sort())!==JSON.stringify(keys.sort()))throw Error('invalid_projection_schema');
 if(! /^[0-9a-f-]{36}$/.test(p.event_id)||! /^[0-9a-f-]{36}$/.test(p.application_id)||! /^[0-9a-f-]{36}$/.test(p.request_id)||!Number.isSafeInteger(p.revision)||p.revision<1)throw Error('invalid_projection_id');
 const groups=[[p.candidate,20],[p.application,7],...(p.history||[]).map(r=>[r,9]),...(p.privacy||[]).map(r=>[r,11]),...(p.requests||[]).map(r=>[r,10])];
 for(const [row,size] of groups){if(!Array.isArray(row)||row.length!==size||row.some(v=>!['string','number','boolean'].includes(typeof v)||(typeof v==='string'&&v.length>1000)))throw Error('invalid_projection_value');}
 if(!Array.isArray(p.history)||!Array.isArray(p.privacy)||!Array.isArray(p.requests)||p.history.length>200||p.privacy.length>200||p.requests.length>100)throw Error('projection_too_large');
 const cid=p.candidate[0];if(! /^EWU-[0-9a-f]{32}$/.test(cid)||p.application[0]!==p.application_id||p.application[1]!==cid||p.application[6]!==p.revision||p.candidate[19]!==p.revision||!EWU_COMMAND_STATUSES.includes(p.application[3]))throw Error('projection_identity_mismatch');
 if(p.history.some(r=>r[1]!==p.application_id||r[2]!==cid)||p.privacy.some(r=>r[1]!==cid)||p.requests.some(r=>r[1]!==cid))throw Error('projection_scope_mismatch');
 const lock=LockService.getScriptLock();lock.waitLock(10000);
 try{
  const book=SpreadsheetApp.openById(sheetId),sheets={};
  for(const name of ['Candidates','Applications','Candidate Journey','RODO Register','Data Requests'])sheets[name]=ewuSheet_(book,name,EWU_OPERATIONAL_SCHEMA[name]);
  const journal=ewuSheet_(book,'_EWU Receipts',EWU_RECEIPT_HEADERS);
  const hash=ewuHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,ewuCanonical_({...p,request_id:''}),Utilities.Charset.UTF_8));
  const previous=ewuRows_(journal,5).find(r=>r[0]===p.event_id);
  if(previous&&previous[3]!==hash)throw Error('event_conflict');
  if(!previous){
   const old=ewuRows_(sheets.Applications,11).find(r=>r[0]===p.application_id);
   if(old&&old[1]!==cid)throw Error('candidate_reassignment_refused');
   if(old&&Number(old[6])===p.revision&&JSON.stringify(old.slice(0,7))!==JSON.stringify(p.application))throw Error('revision_conflict');
   if(!old||Number(old[6])<=p.revision){
    // Write only the server-owned first seven fields; preserve status requests.
    ewuPut_(sheets.Applications,p.application,11);
    const candidate=ewuRows_(sheets.Candidates,20).find(r=>r[0]===cid);
    if(!candidate||String(candidate[15])<=String(p.candidate[15]))ewuPut_(sheets.Candidates,p.candidate,20);
   }
   for(const row of p.history)ewuPut_(sheets['Candidate Journey'],row,9);
   for(const row of p.privacy)ewuPut_(sheets['RODO Register'],row,11);
   for(const row of p.requests){
    const current=ewuRows_(sheets['Data Requests'],10).find(r=>r[0]===row[0]);
    if(!current)ewuPut_(sheets['Data Requests'],row,10);
   }
   journal.appendRow([p.event_id,p.application_id,p.revision,hash,new Date().toISOString()]);SpreadsheetApp.flush();
  }
  const result={application_id:p.application_id,revision:p.revision,ok:true};
  const response={request_id:p.request_id,result:result,sheet_id:sheetId};
  return ewuBody_({...response,signature:ewuMac_(ewuCanonical_(response),secret)});
 }finally{lock.releaseLock();}
}

function setupEWUOperational(){
 const id=PropertiesService.getScriptProperties().getProperty('SHEET_ID');if(!id)throw Error('SHEET_ID missing');
 const book=SpreadsheetApp.openById(id);
 for(const [name,headers] of Object.entries(EWU_OPERATIONAL_SCHEMA)){
  let sheet=book.getSheetByName(name);
  if(!sheet){sheet=book.insertSheet(name);sheet.getRange(1,1,1,headers.length).setValues([headers]);}
  ewuSheet_(book,name,headers);sheet.setFrozenRows(1);sheet.getRange(1,1,1,headers.length).setBackground('#eeeeee').setFontWeight('bold').setWrap(true);sheet.setRowHeight(1,40);
  if(!['Dashboard','Settings'].includes(name)&&!sheet.getFilter())sheet.getRange(1,1,sheet.getMaxRows(),headers.length).createFilter();
  if(!['Vacancies'].includes(name)){
   const protection=sheet.protect().setDescription('EWU server-owned fields');
   protection.removeEditors(protection.getEditors());if(protection.canDomainEdit())protection.setDomainEdit(false);
   if(name==='Applications')protection.setUnprotectedRanges([sheet.getRange(2,8,sheet.getMaxRows()-1,1)]);
  }
 }
 let receipt=book.getSheetByName('_EWU Receipts');
 if(!receipt){receipt=book.insertSheet('_EWU Receipts');receipt.getRange(1,1,1,5).setValues([EWU_RECEIPT_HEADERS]);receipt.hideSheet();}
 ewuSheet_(book,'_EWU Receipts',EWU_RECEIPT_HEADERS);
 const protection=receipt.protect().setDescription('EWU delivery journal');protection.removeEditors(protection.getEditors());if(protection.canDomainEdit())protection.setDomainEdit(false);
 const rule=SpreadsheetApp.newDataValidation().requireValueInList(EWU_COMMAND_STATUSES,true).setAllowInvalid(false).build();
 const apps=book.getSheetByName('Applications');apps.getRange(2,8,apps.getMaxRows()-1,1).setDataValidation(rule);
 setupEWUCommands();SpreadsheetApp.flush();
}
