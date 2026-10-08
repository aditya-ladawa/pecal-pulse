import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const code = ts.transpileModule(readFileSync(new URL('../src/modules/chat/audio-output.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};
new Function('module','exports',code)(mod,mod.exports);
const {pickSpeakerOutput}=mod.exports;

test('keeps the saved speaker while it is plugged in',()=>{
 const devices=[{deviceId:'sounddrum',label:'SoundDrum'},{deviceId:'hdmi',label:'HDMI'}];
 assert.equal(pickSpeakerOutput(devices,'hdmi'),'hdmi');
});

test('lone SoundDrum is picked despite default+communications pseudo-devices',()=>{
 const devices=[{deviceId:'default',label:''},{deviceId:'communications',label:''},{deviceId:'sounddrum',label:'SoundDrum'}];
 assert.equal(pickSpeakerOutput(devices,''),'sounddrum');
});

test('saved-but-unplugged falls back to the lone speaker',()=>{
 const devices=[{deviceId:'default',label:''},{deviceId:'sounddrum',label:'SoundDrum'}];
 assert.equal(pickSpeakerOutput(devices,'old-gone'),'sounddrum');
});

test('two real speakers means the system default, no guessing',()=>{
 const devices=[{deviceId:'default',label:''},{deviceId:'sounddrum',label:'SoundDrum'},{deviceId:'hdmi',label:'HDMI'}];
 assert.equal(pickSpeakerOutput(devices,''),'');
});
