// Explicit activation prevents an unconfigured PR/preview from polling the live bot.
if(process.env.EWU_RUNTIME_ENABLED!=='1')throw new Error('Runtime activation requires reviewed rollout');
import http from 'node:http';
import fs from 'node:fs';
import pg from 'pg';
import {DurableInbox,processUpdate,syncOne} from './sync.mjs';
import {createBot} from './bot-core.mjs';
import {enqueue,deliverOne,errorCode} from './delivery.mjs';
import {acquireIntakeLock} from './intake-lock.mjs';
const TOKEN=process.env.TELEGRAM_TOKEN,DB=process.env.DATABASE_URL;
const processingMode=process.env.EWU_PROCESSING_MODE||'full';
if(!['full','intake'].includes(processingMode))throw new Error('Invalid processing mode');
const directory=process.env.EWU_INBOX_DIR;
const key=Buffer.from(process.env.EWU_INBOX_KEY||'','base64');
if(!TOKEN||!DB||!directory||key.length!==32)throw new Error('Required runtime configuration missing');
// Production intake must reside on a mounted persistent volume, never /tmp or image disk.
const mounts=fs.readFileSync('/proc/self/mountinfo','utf8').split('\n').map(x=>x.split(' ')[4]);
if(!mounts.some(m=>m && m!=='/' && (directory===m||directory.startsWith(m+'/'))))throw new Error('Persistent intake mount required');
fs.mkdirSync(directory,{recursive:true,mode:0o700});
const {Pool}=pg;
const pool=new Pool({connectionString:DB,max:5,connectionTimeoutMillis:5000,statement_timeout:10000,idle_in_transaction_session_timeout:120000});
pool.on('error',()=>{health.database=false;console.error('database pool unavailable')});
const health={ready:false,database:false,pending:null,blocked:null,mode:processingMode};
let stopping=false,box,lock,controller;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function log(component,e){console.error(JSON.stringify({component,code:errorCode(e)}))}
async function telegram(method,body={}) {
 const own=new AbortController();controller=method==='getUpdates'?own:controller;
 const signal=AbortSignal.any([own.signal,AbortSignal.timeout(method==='getUpdates'?60000:15000)]);
 const response=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body),signal});
 let d;
 try{d=await response.json()}catch{throw Object.assign(new Error('Invalid Telegram response'),{code:'TG_RESPONSE'})}
 if(!d.ok){const code=Number(d.error_code||response.status);throw Object.assign(new Error('Telegram request failed'),{code:'TG_'+code,permanent:[400,401,403].includes(code),retryAfter:d.parameters?.retry_after})}
 return d.result;
}
const bot=createBot({pool,enqueue,adminIds:String(process.env.EWU_ADMIN_IDS||'').split(',').filter(Boolean),aiEnabled:Boolean(process.env.AI_GATEWAY_API_KEY&&process.env.AI_MODEL),aiModel:process.env.AI_MODEL||''});
async function intake() {
 while(!stopping){
  try {
   const updates=await telegram('getUpdates',{offset:box.offset(),timeout:50,allowed_updates:['message']});
   // NEVER make another getUpdates request until this full batch is fsynced.
   box.ingest(updates);health.ready=true;
  }catch(e){health.ready=false;log('intake',e);if(e.code==='TG_409'||e.code==='TG_401'){process.exitCode=1;stopping=true;break}if(!stopping)await sleep(3000)}
 }
}
async function consume() {
 while(!stopping){
  try {
   for(const u of box.pending()){
    if(stopping)break;
    await processUpdate(pool,box.botId,u,(client,update)=>bot.apply(client,update,box.botId));
    box.acknowledge(u.update_id);
   }
   health.database=true;
  }catch(e){health.database=false;log('update_consumer',e)}
  await sleep(1000);
 }
}
async function worker(name,fn) {
 while(!stopping){try{const worked=await fn();if(!worked)await sleep(1000)}catch(e){log(name,e);await sleep(3000)}}
}
async function monitor(){
 while(!stopping){
  try{
   const r=await pool.query(`SELECT (SELECT count(*) FROM ewu_sync_jobs WHERE completed_at IS NULL)::int AS sync,
    (SELECT count(*) FROM ewu_delivery_jobs WHERE sent_at IS NULL)::int AS delivery,
    (SELECT count(*) FROM ewu_delivery_jobs WHERE blocked AND sent_at IS NULL)::int AS blocked,
    (SELECT count(*) FROM ewu_applications a WHERE kind='candidate' AND NOT EXISTS(SELECT 1 FROM candidates c WHERE c.ewu_application_id=a.id))::int AS missing_candidates`);
   health.database=true;health.pending={inbox:box.pending().length,...r.rows[0]};health.blocked=r.rows[0].blocked;
  }catch(e){health.database=false;log('monitor',e)}
  await sleep(15000);
 }
}
const server=http.createServer((req,res)=>{
 if(req.url!=='/api/health'){res.writeHead(404);return res.end()}
 res.writeHead(health.ready&&!stopping?200:503,{'content-type':'application/json'});
 res.end(JSON.stringify({ok:health.ready&&!stopping,...health}));
});
async function run(){
 lock=await acquireIntakeLock(directory);
 lock.child.once('exit',()=>{if(!stopping){health.ready=false;stopping=true;controller?.abort()}});
 // Read-only setup. Never delete a webhook or change the bot profile implicitly.
 const me=await telegram('getMe'),hook=await telegram('getWebhookInfo');
 if(hook.url)throw new Error('Webhook configured: separate migration approval required');
 box=new DurableInbox(directory,key,me.id);box.botId=me.id;
 if(processingMode==='full'){
 const r=await pool.query("SELECT value FROM ewu_settings WHERE key='recruitment_group_chat_id'");
 if(!r.rows[0]?.value)throw new Error('Recruitment group binding required');
 await pool.query('SELECT 1 FROM ewu_delivery_jobs LIMIT 0');
 await pool.query('SELECT 1 FROM ewu_sync_jobs LIMIT 0');
 await pool.query('SELECT 1 FROM ewu_processed_updates LIMIT 0');
 const group=await telegram('getChat',{chat_id:r.rows[0].value});
 if(!['group','supergroup'].includes(group.type))throw new Error('Recruitment destination must be a group');
 }
 // One process owns the mounted intake lock before starting polling.
 health.ready=true;server.listen(Number(process.env.PORT||3000),'0.0.0.0');
 console.log('EWU durable runtime ready');
 if(processingMode==='intake')await intake();
 else await Promise.all([intake(),consume(),worker('candidate_sync',()=>syncOne(pool)),worker('telegram_delivery',()=>deliverOne(pool,telegram)),monitor()]);
}
function shutdown(){if(stopping)return;stopping=true;health.ready=false;controller?.abort();setTimeout(()=>process.exit(1),65000).unref()}
process.once('SIGTERM',shutdown);process.once('SIGINT',shutdown);
try{await run()}catch(e){log('startup',e);process.exitCode=1}
finally{stopping=true;controller?.abort();server.close();await pool.end();lock?.release()}
