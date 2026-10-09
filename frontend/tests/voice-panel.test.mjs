import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const code = ts.transpileModule(
  readFileSync(
    new URL("../src/modules/chat/VoicePanel.tsx", import.meta.url),
    "utf8",
  ),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
    },
  },
).outputText;
const flush = () => new Promise((resolve) => setImmediate(resolve));

function harness(language, transcript) {
  const slots = [],
    effects = [],
    sent = [],
    spoken = [],
    timers = new Set();
  let cursor = 0;
  const state = {
    assistantLanguage: language,
    voiceResponse: null,
    messages: [],
    voiceBusy: false,
    voiceInputPending: false,
    apiStatus: "connected",
    chatStatus: { configured: true },
    chatLoading: false,
  };
  state.set = (patch) => Object.assign(state, patch);
  const store = (select) => select(state);
  store.getState = () => state;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [
        slots[index],
        (value) => {
          slots[index] = value;
        },
      ];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useCallback(fn) {
      cursor++;
      return fn;
    },
    useEffect(fn, deps) {
      const index = cursor++;
      const previous = slots[index];
      if (!deps || !previous || deps.some((dep, i) => dep !== previous[i]))
        effects.push(fn);
      slots[index] = deps;
    },
  };
  class Voice {
    room = {};
    start = async () => true;
    finish = async () => transcript;
    speak = async (text) => spoken.push(text);
    cancel = async () => {};
    close() {}
    microphone() {
      return {};
    }
  }
  const aui = {
    thread: {
      append: async (message) => {
        sent.push({ message, voiceTurn: state.voiceInputPending });
        state.voiceInputPending = false; // SalesAssistantProvider consumes this at send time.
      },
      cancelRun() {},
    },
    composer: {
      getState: () => ({ text: "An unfinished typed draft" }),
      setText() {
        throw new Error(
          "Voice must not replace a typed draft or require manual Send",
        );
      },
    },
  };
  const exports = {};
  const context = {
    exports,
    console,
    require(name) {
      if (name === "react") return react;
      if (name === "react/jsx-runtime")
        return {
          jsx: (type, props) => ({ type, props }),
          jsxs: (type, props) => ({ type, props }),
        };
      if (name === "@assistant-ui/react")
        return {
          useAui: () => aui,
          useAuiState: (select) => select({ thread: { isRunning: false } }),
        };
      if (name.includes("sales/store")) return { useSalesStore: store };
      if (name.includes("voice-livekit")) return { LiveKitVoice: Voice };
      if (name.includes("create-livekit-adapter"))
        return {
          createLiveKitAdapter: () => ({ setTrack() {}, dispose() {} }),
        };
      if (name.includes("audio-output")) return { pickSpeakerOutput: () => "" };
      if (name === "@livekit/components-react")
        return {
          RoomContext: { Provider: "room" },
          RoomAudioRenderer: "audio",
        };
      return {};
    },
    navigator: {
      mediaDevices: {
        enumerateDevices: async () => [],
        addEventListener() {},
        removeEventListener() {},
      },
    },
    localStorage: { getItem: () => null },
    window: { addEventListener() {}, removeEventListener() {} },
    fetch: async () => ({ json: async () => ({ configured: true }) }),
    AbortController,
    setTimeout(fn) {
      timers.add(fn);
      return fn;
    },
    clearTimeout(fn) {
      timers.delete(fn);
    },
  };
  vm.runInNewContext(code, context);
  function render() {
    cursor = 0;
    const tree = exports.VoicePanel();
    for (const fn of effects.splice(0)) fn();
    return tree;
  }
  function find(tree, label) {
    if (!tree || typeof tree !== "object") return null;
    if (tree.props?.["aria-label"] === label) return tree;
    return [tree.props?.children]
      .flat(Infinity)
      .map((child) => find(child, label))
      .find(Boolean);
  }
  return { state, sent, spoken, render, find };
}

test("spoken request automatically enters the agent runtime and final reply is spoken, in either language", async () => {
  for (const language of ["en", "de"]) {
    const transcript =
      language === "en" ? "Open the customers page." : "Öffne die Kundenseite.";
    const h = harness(language, transcript);
    h.render();
    await flush();
    let tree = h.render();
    h.find(tree, "Start voice request").props.onClick();
    await flush();
    tree = h.render();
    h.find(tree, "Send voice request").props.onClick();
    await flush();
    assert.equal(h.sent.length, 1, "no manual textbox Send is required");
    assert.equal(
      h.sent[0].voiceTurn,
      true,
      "runtime must request automatic spoken output",
    );
    assert.equal(
      h.sent[0].message.content[0].text,
      transcript,
      "recognized words reach tools unchanged",
    );
    assert.equal(h.state.voiceBusy, false);
    h.state.voiceResponse = {
      id: "final",
      kind: "final",
      text:
        language === "en"
          ? "Opening Customers."
          : "Die Kundenseite wird geöffnet.",
    };
    h.render();
    await flush();
    h.render();
    await flush();
    assert.equal(
      h.spoken.length,
      1,
      "speak completed reply once, including after workspace updates",
    );
    assert.equal(h.spoken[0], h.state.voiceResponse.text);
  }
});

test("unclear speech never sends a blank agent command", async () => {
  const h = harness("en", null);
  h.render();
  await flush();
  h.find(h.render(), "Start voice request").props.onClick();
  await flush();
  h.find(h.render(), "Send voice request").props.onClick();
  await flush();
  assert.equal(h.sent.length, 0);
  assert.equal(h.state.voiceBusy, false);
});
