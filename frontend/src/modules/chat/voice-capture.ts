export async function captureVoice() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    video: false,
  });
  let context: AudioContext;
  try {
    context = new AudioContext({ sampleRate: 24000 });
  } catch (error) {
    stream.getTracks().forEach((track) => track.stop());
    throw error;
  }
  const chunks: Float32Array[] = [];
  let length = 0;
  let node: AudioWorkletNode | null = null;
  const release = () => {
    node?.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
  };
  try {
    await context.audioWorklet.addModule("/voice-capture.js");
    await context.resume();
    node = new AudioWorkletNode(context, "voice-capture");
    node.port.onmessage = (event: MessageEvent<Float32Array>) => {
      if (length >= context.sampleRate * 45) return;
      chunks.push(event.data);
      length += event.data.length;
    };
    const source = context.createMediaStreamSource(stream);
    const silent = context.createGain();
    silent.gain.value = 0;
    source.connect(node).connect(silent).connect(context.destination);
    return {
      cancel: release,
      stop: () => {
        release();
        const buffer = new ArrayBuffer(44 + length * 2);
        const view = new DataView(buffer);
        const write = (offset: number, text: string) =>
          [...text].forEach((char, i) =>
            view.setUint8(offset + i, char.charCodeAt(0)),
          );
        write(0, "RIFF");
        view.setUint32(4, 36 + length * 2, true);
        write(8, "WAVE");
        write(12, "fmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, context.sampleRate, true);
        view.setUint32(28, context.sampleRate * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        write(36, "data");
        view.setUint32(40, length * 2, true);
        let offset = 44;
        for (const chunk of chunks)
          for (const value of chunk) {
            const sample = Math.max(-1, Math.min(1, value));
            view.setInt16(offset, sample * (sample < 0 ? 32768 : 32767), true);
            offset += 2;
          }
        return new Blob([buffer], { type: "audio/wav" });
      },
    };
  } catch (error) {
    release();
    throw error;
  }
}
