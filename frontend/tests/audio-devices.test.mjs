import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const code = ts.transpileModule(readFileSync(new URL('../src/modules/chat/audio-devices.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};
new Function('module','exports',code)(mod,mod.exports);
const {pickAudioDevice}=mod.exports;

test('keeps the explicitly saved device while it is plugged in',()=>{
 const devices=[{deviceId:'buds3',label:'OnePlus Buds 3'},{deviceId:'laptop',label:'MacBook Pro Microphone'}];
 assert.equal(pickAudioDevice(devices,'buds3'),'buds3');
});

test('auto-selects OnePlus Buds 3 when nothing was saved',()=>{
 const devices=[{deviceId:'laptop',label:'MacBook Pro Microphone'},{deviceId:'buds3',label:'OnePlus Buds 3'}];
 assert.equal(pickAudioDevice(devices,''),'buds3');
});

test('saved-but-unplugged falls back to the earpiece, not the void',()=>{
 const devices=[{deviceId:'buds3',label:'OnePlus Buds 3'}];
 assert.equal(pickAudioDevice(devices,'old-gone'),'buds3');
});

test('no match means the system default',()=>{
 const devices=[{deviceId:'laptop',label:'Microphone'}];
 assert.equal(pickAudioDevice(devices,''),'');
});
