import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const code = ts.transpileModule(
  readFileSync(
    new URL("../src/modules/chat/voice-capture.ts", import.meta.url),
    "utf8",
  ),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;

function setup() {
  let node,
    stopped = 0,
    requested;
  const exports = {};
  const track = {
    stop: () => stopped++,
    getSettings: () => ({ deviceId: "headset" }),
    label: "Test headset",
  };
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  class Context {
    sampleRate = 24000;
    audioWorklet = { addModule: async () => {} };
    resume = async () => {};
    close = async () => {};
    createMediaStreamSource = () => ({ connect: () => node });
    createGain = () => ({ gain: { value: 1 }, connect: () => {} });
  }
  class Worklet {
    port = { onmessage: null };
    constructor() {
      node = this;
    }
    connect = (output) => output;
    disconnect = () => {};
  }
  vm.runInNewContext(code, {
    exports,
    Blob,
    AudioContext: Context,
    AudioWorkletNode: Worklet,
    navigator: {
      mediaDevices: {
        getUserMedia: async (options) => {
          requested = options;
          return stream;
        },
      },
    },
  });
  return {
    capture: exports.captureVoice,
    feed: (samples) => node.port.onmessage({ data: samples }),
    get stopped() {
      return stopped;
    },
    get requested() {
      return requested;
    },
  };
}

test("captured PCM reaches the WAV with a real level and selected input", async () => {
  const env = setup(),
    levels = [],
    devices = [];
  const recording = await env.capture({
    deviceId: "headset",
    onLevel: (level) => levels.push(level),
    onDevice: (device) => devices.push(device),
  });
  for (let n = 0; n < 30; n++)
    env.feed(
      Float32Array.from({ length: 256 }, (_, i) => Math.sin(i / 5) * 0.1),
    );
  const data = new DataView(await recording.stop().arrayBuffer());
  assert.equal(data.getUint32(24, true), 24000);
  assert.equal(data.getUint32(40, true), 30 * 256 * 2);
  assert.notEqual(data.getInt16(46, true), 0);
  assert.ok(levels.some((level) => level > 0));
  assert.equal(levels.at(-1), 0);
  assert.equal(env.requested.audio.deviceId.exact, "headset");
  assert.equal(devices[0].label, "Test headset");
  assert.equal(env.stopped, 1);
});

test("silent input stops the microphone and is not uploaded as speech", async () => {
  const env = setup(),
    recording = await env.capture();
  env.feed(new Float32Array(24000));
  assert.throws(() => recording.stop(), /No microphone sound recorded/);
  assert.equal(env.stopped, 1);
});

test("a premature release is identified as too short, and cancellation stops input", async () => {
  const env = setup(),
    recording = await env.capture();
  env.feed(new Float32Array([0.1]));
  assert.throws(() => recording.stop(), /Recording was too short/);
  const other = setup(),
    canceled = await other.capture();
  canceled.cancel();
  assert.equal(other.stopped, 1);
});
