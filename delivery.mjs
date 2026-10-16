export function errorCode(error) {
 const code=String(error?.code||'UNKNOWN');
 return /^[0-9A-Z_]{1,32}$/.test(code)?code:'UNKNOWN';
}
export async function journal(client, component, reference, error) {
 await client.query('INSERT INTO ewu_error_events(component,reference_id,error_code) VALUES($1,$2,$3)',[component,String(reference),errorCode(error)]);
}
export async function enqueue(client, botId, updateId, ordinal, body) {
 await client.query('INSERT INTO ewu_delivery_jobs(bot_id,update_id,ordinal,chat_id,payload) VALUES($1,$2,$3,$4,$5) ON CONFLICT(bot_id,update_id,ordinal) DO NOTHING',[String(botId),updateId,ordinal,String(body.chat_id),JSON.stringify(body)]);
}
export async function deliverOne(pool, telegram, random=Math.random) {
 const c=await pool.connect();
 try {
  await c.query('BEGIN');
  // A failed earlier message blocks only its chat, preserving question ordering.
  const r=await c.query(`SELECT j.* FROM ewu_delivery_jobs j
    WHERE j.sent_at IS NULL AND NOT j.blocked AND j.next_attempt_at<=now()
    AND NOT EXISTS(SELECT 1 FROM ewu_delivery_jobs p WHERE p.chat_id=j.chat_id AND p.id<j.id AND p.sent_at IS NULL)
    ORDER BY j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1`);
  if(!r.rowCount){await c.query('COMMIT');return false}
  const job=r.rows[0];
  let receipt;
  try { receipt=await telegram('sendMessage',job.payload); }
  catch(error) {
   const blocked=error.permanent===true;
   const delay=Math.max(Number(error.retryAfter)||0,Math.min(3600,2**Math.min(job.attempts+1,11))*(.5+random()));
   await journal(c,'telegram_delivery',job.id,error);
   await c.query("UPDATE ewu_delivery_jobs SET attempts=attempts+1,next_attempt_at=now()+$2*interval '1 second',blocked=$3,last_error_code=$4 WHERE id=$1",[job.id,delay,blocked,errorCode(error)]);
   await c.query('COMMIT');return true;
  }
  // If this commit fails AFTER Telegram accepts, retry can duplicate the message.
  // Telegram sendMessage has no idempotency key. No exactly-once claim is made.
  await c.query('UPDATE ewu_delivery_jobs SET sent_at=now(),telegram_message_id=$2,attempts=attempts+1,last_error_code=NULL WHERE id=$1',[job.id,receipt.message_id]);
  await c.query('INSERT INTO ewu_messages(id,telegram_id,direction,body) VALUES(gen_random_uuid(),$1,\'out\',$2)',[String(job.chat_id),String(job.payload.text)]);
  await c.query('COMMIT');return true;
 } catch(e) {await c.query('ROLLBACK').catch(()=>{});throw e}
 finally {c.release()}
}
