import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const code = ts.transpileModule(
  readFileSync(
    new URL("../src/modules/chat/voice-playback.ts", import.meta.url),
    "utf8",
  ),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;
const flush = () => new Promise((resolve) => setImmediate(resolve));
function setup(synthesize) {
  const exports = {},
    calls = [],
    sources = [],
    errors = [];
  const context = {
    state: "running",
    resume: async () => {},
    close: async () => {},
    decodeAudioData: async () => ({}),
    destination: {},
    createBufferSource() {
      const source = {
        buffer: null,
        connect() {},
        start() {
          sources.push(source);
        },
        stop() {
          source.onended?.();
        },
        onended: null,
      };
      return source;
    },
  };
  vm.runInNewContext(code, { exports, AbortController, Error });
  const playback = new exports.VoicePlayback({
    createContext: () => context,
    onState() {},
    onError: (message) => errors.push(message),
    synthesize: async (text, signal) => {
      calls.push({ text, signal });
      return synthesize ? synthesize(text, signal) : new ArrayBuffer(8);
    },
  });
  return { playback, calls, sources, errors };
}

test("progress is audible before final; later updates do not abort active speech", async () => {
  const env = setup();
  await env.playback.unlock();
  env.playback.enqueue({ text: "Checking accounts.", kind: "progress" });
  await flush();
  assert.equal(env.sources.length, 1);
  env.playback.enqueue({ text: "Intermediate progress", kind: "progress" });
  env.playback.enqueue({ text: "Latest progress", kind: "progress" });
  assert.equal(env.calls[0].signal.aborted, false);
  env.sources[0].onended();
  await flush();
  assert.equal(env.calls[1].text, "Latest progress");
  env.playback.enqueue({ text: "Found five accounts.", kind: "final" });
  env.sources[1].onended();
  await flush();
  assert.equal(env.calls[2].text, "Found five accounts.");
  assert.equal(env.sources.length, 3);
  env.sources[2].onended();
  env.playback.close();
});

test("final/error summaries replace stale queued progress and can be spoken after failure", async () => {
  const env = setup();
  await env.playback.unlock();
  env.playback.enqueue({ text: "Checking", kind: "progress" });
  await flush();
  env.playback.enqueue({ text: "Old progress", kind: "progress" });
  env.playback.enqueue({ text: "Provider timed out.", kind: "error" });
  env.sources[0].onended();
  await flush();
  assert.deepEqual(
    env.calls.map((call) => call.text),
    ["Checking", "Provider timed out."],
  );
  env.playback.close();
});

test("cancelling in-flight synthesis cannot start stale audio; next reply still plays", async () => {
  let release;
  const env = setup((text) =>
    text === "Old"
      ? new Promise((resolve) => {
          release = resolve;
        })
      : new ArrayBuffer(8),
  );
  await env.playback.unlock();
  env.playback.enqueue({ text: "Old", kind: "progress" });
  await flush();
  env.playback.cancel();
  env.playback.enqueue({ text: "New", kind: "final" });
  await flush();
  release(new ArrayBuffer(8));
  await flush();
  assert.equal(env.calls[0].signal.aborted, true);
  assert.equal(env.sources.length, 1);
  env.playback.close();
});

test("synthesis failure is visible and does not prevent a later replay", async () => {
  const env = setup((text) => {
    if (text === "Fail") throw new Error("Speech service unavailable");
    return new ArrayBuffer(8);
  });
  await env.playback.unlock();
  env.playback.enqueue({ text: "Fail", kind: "error" });
  await flush();
  assert.deepEqual(env.errors, ["Speech service unavailable"]);
  env.playback.enqueue({ text: "Replay", kind: "final" });
  await flush();
  assert.equal(env.sources.length, 1);
  env.playback.close();
});
