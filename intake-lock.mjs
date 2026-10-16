import {spawn} from 'node:child_process';
import path from 'node:path';
// POSIX flock is kernel-released on process death; no stale PID files to delete.
export async function acquireIntakeLock(directory) {
 const child=spawn('flock',['--nonblock','--no-fork',path.join(directory,'intake.lock'),process.execPath,'--input-type=module','-e',"console.log('LOCKED');process.stdin.resume()"],{stdio:['pipe','pipe','ignore']});
 await new Promise((resolve,reject)=>{
  let ready=false;
  child.once('error',reject);
  child.once('exit',()=>{if(!ready)reject(new Error('Intake lock unavailable'))});
  child.stdout.once('data',data=>{if(String(data).trim()==='LOCKED'){ready=true;resolve()}else reject(new Error('Lock handshake failed'))});
 });
 return {child, release:()=>child.stdin.end()};
}
