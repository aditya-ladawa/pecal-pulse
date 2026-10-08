import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const code = ts.transpileModule(readFileSync(new URL('../src/modules/chat/voice-livekit.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const flush=()=>new Promise(r=>setImmediate(r));
function setup() {
 const calls=[], requests=[], timeouts=[]; let release;
 class Room {
  state='disconnected';
  on(){return this;}
  startAudio=async()=>calls.push('unlock');
  connect=async()=>{calls.push('connect');this.state='connected';};
  disconnect=async()=>{calls.push('disconnect');this.state='disconnected';};
  localParticipant={
   setMicrophoneEnabled:async value=>calls.push(value?'mic-on':'mic-off'),
   performRpc:async ({method,payload,responseTimeout})=>{calls.push(method);timeouts.push({method,responseTimeout});if(method==='speak')calls.push(JSON.parse(payload));return method==='end_turn'?JSON.stringify({text:'Due soon',turn_id:'turn1'}):'';},
  };
 }
 const exports={};
 const context={exports,crypto:{randomUUID:()=> 'session'},require:()=>({Room,ConnectionState:{Connected:'connected'},RoomEvent:{},Track:{Source:{Microphone:'mic'}}}),fetch:async(url,options)=>{requests.push({url,options});if(release && url.endsWith("/connect"))await new Promise(r=>release=r);return {ok:true,json:async()=>({server_url:'wss://example',token:'participant',agent_identity:'pulse-voice'})};}};
 vm.runInNewContext(code,context);
 const voice=new exports.LiveKitVoice({onSpeaking(){},onError(){}});
  return {voice,calls,requests,timeouts,delay:()=>{release=true;},release:()=>release()};
}

test('microphone streams only during the explicit turn; final ties to turn ID',async()=>{
 const {voice,calls}=setup();assert.equal(await voice.start(''),true);
 assert.equal(await voice.finish(),'Due soon');await voice.speak('Found two accounts.');
 assert.ok(calls.indexOf('start_turn')<calls.indexOf('mic-on'));
 assert.ok(calls.indexOf('mic-off')<calls.indexOf('end_turn'));
 assert.equal(calls.at(-1).turn_id,'turn1');
 voice.close();
});
test('release during connection cannot start a late microphone',async()=>{
 const s=setup();s.delay();const pending=s.voice.start('');await flush();await s.voice.cancel();s.release();
 assert.equal(await pending,false);assert.ok(!s.calls.includes('mic-on'));s.voice.close();
});
test('close during connection discards credentials and never joins',async()=>{
 const s=setup();s.delay();const pending=s.voice.start('');await flush();s.voice.close();s.release();
 assert.equal(await pending,false);assert.ok(!s.calls.includes('connect'));
 assert.ok(s.requests.some(r=>r.url.endsWith('/stop')));
});
test('rpc timeouts are millisecond-scale, never below the client 8000ms floor',async()=>{
 const {voice,timeouts}=setup();await voice.start('');await voice.finish();await voice.speak('Found two accounts.');await voice.cancel();
 assert.ok(timeouts.length>=4);
 for(const {method,responseTimeout} of timeouts)assert.ok(responseTimeout>=8000,`${method} timeout ${responseTimeout} would expire instantly`);
 voice.close();
});
test('warm room is reused and cancellation interrupts the remote speech',async()=>{
 const {voice,calls}=setup();await voice.start('');await voice.finish();await voice.cancel();await voice.start('');
 assert.equal(calls.filter(c=>c==='connect').length,1);assert.ok(calls.includes('interrupt'));voice.close();
});
