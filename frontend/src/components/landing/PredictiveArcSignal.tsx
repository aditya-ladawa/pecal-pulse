"use client";
import { useEffect, useRef } from "react";

const MAX_DPR = 2;

const VERT_SRC = `
attribute vec2 a_pos;
void main(){ gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAG_SRC = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec2  uRes;
uniform float uTime, uDpr, uCell, uDot, uHover;
uniform vec2  uPtr;
uniform float uA, uB, uC, uD;
uniform vec3  uBg, uBase, uAccent, uHigh;

void main(){
  float cs = max(uCell, 2.0);
  vec2 ci = floor(gl_FragCoord.xy / cs);
  vec2 cc = (ci + 0.5) * cs;

  float x = cc.x / uDpr;
  float y = (uRes.y - cc.y) / uDpr;
  float w = uRes.x / uDpr;
  float h = uRes.y / uDpr;
  float t = uTime;

  float i = 0.0;
  float k = 6.2831853 / max(w * uC, 1.0);
  float y0 = h * uA + h * uB * (sin(x * k - t * 1.2) + 0.35 * sin(x * k * 2.3 + t * 0.9)) / 1.35;
  float gx = (x - uPtr.x) / (w * 0.12);
  float curveY = y0 + (uPtr.y - h * 0.5) * exp(-gx * gx) * 0.8 * uHover;
  float dist = abs(y - curveY);
  float normX = (x - w * 0.5) / (w * 0.75);
  float th = (70.0 + 30.0 * sin(x * k * 0.5 + t * 0.7)) * uD;
  if (dist < th) {
    i = 1.0 - dist / th;
    float waveX = sin(x * 0.015 + t);
    float waveY = cos(y * 0.02 + t);
    i = i * 0.7 + waveX * waveY * 0.3 * i;
    i *= max(0.0, 1.0 - pow(abs(normX), 2.5));
  }

  vec3 col = uBg;
  if (i > 0.02) {
    float side = uDot * i * uDpr;
    vec2 d = abs(gl_FragCoord.xy - cc);
    float cov = 1.0 - smoothstep(side * 0.5 - 1.0, side * 0.5 + 1.0, length(d));

    vec3 ink = mix(uBase, uAccent, clamp(pow(i, 1.1), 0.0, 1.0));
    ink = mix(ink, uHigh, smoothstep(0.72, 1.0, i));
    col = mix(uBg, ink, cov * clamp(i * 1.6, 0.0, 1.0));
  }
  gl_FragColor = vec4(col, 1.0);
}
`;

function compile(
  gl: WebGLRenderingContext,
  type: number,
  src: string,
): WebGLShader | null {
  const sh = gl.createShader(type);
  if (!sh) return null;
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.error("PredictiveArcSignal shader:", gl.getShaderInfoLog(sh));
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

function parseColor(
  input: string | undefined,
  fb: [number, number, number],
): [number, number, number] {
  if (!input) return fb;
  const str = String(input).trim();
  if (str.charAt(0) === "#") {
    let hex = str.slice(1);
    if (hex.length === 3 || hex.length === 4) {
      hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    }
    if (hex.length >= 6) {
      const r = parseInt(hex.slice(0, 2), 16);
      const g = parseInt(hex.slice(2, 4), 16);
      const b = parseInt(hex.slice(4, 6), 16);
      if (!isNaN(r) && !isNaN(g) && !isNaN(b))
        return [r / 255, g / 255, b / 255];
    }
    return fb;
  }
  const m = str.match(/[\d.]+/g);
  if (m && m.length >= 3) {
    return [
      Math.min(255, parseFloat(m[0])) / 255,
      Math.min(255, parseFloat(m[1])) / 255,
      Math.min(255, parseFloat(m[2])) / 255,
    ];
  }
  return fb;
}

function num(v: unknown, fb: number): number {
  return typeof v === "number" && isFinite(v) ? v : fb;
}

function clampN(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

export interface SignalGroup {
  level?: number;
  amplitude?: number;
  wavelength?: number;
  thickness?: number;
}

const SIGNAL_DEFAULTS: Required<SignalGroup> = {
  level: 50,
  amplitude: 18,
  wavelength: 60,
  thickness: 100,
};

export interface PredictiveArcSignalProps {
  style?: React.CSSProperties;
  width?: number;
  height?: number;
  background?: string;
  baseColor?: string;
  accentColor?: string;
  highlight?: string;
  density?: number;
  dotSize?: number;
  speed?: number;
  hover?: number;
  signal?: SignalGroup;
}

export function PredictiveArcSignal(props: PredictiveArcSignalProps) {
  const {
    style,
    background = "#20384a",
    baseColor = "#274c67",
    accentColor = "#2c5d81",
    highlight = "#ff6f00",
    density = 160,
    dotSize = 100,
    speed = 50,
    hover = 100,
    signal = { level: 50, amplitude: 18, thickness: 100, wavelength: 60 },
    width,
    height,
  } = props;

  const grp = { ...SIGNAL_DEFAULTS, ...(signal || {}) };

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ptrRef = useRef({ tx: 0.5, ty: 0.5, x: 0.5, y: 0.5 });
  const sizeRef = useRef({ w: 0, h: 0 });
  sizeRef.current = { w: num(width, 0), h: num(height, 0) };

  const vRef = useRef<Record<string, number | string>>({});
  vRef.current = {
    bg: background,
    base: baseColor,
    accent: accentColor,
    high: highlight,
    density: Math.round(clampN(num(density, 160), 40, 320)),
    dotSize: clampN(num(dotSize, 100), 20, 400) / 100,
    speed: clampN(num(speed, 50), 0, 100) / 50,
    hover: clampN(num(hover, 100), 0, 200) / 100,
    level: clampN(num(grp.level, 50), 0, 100) / 100,
    amplitude: clampN(num(grp.amplitude, 18), 0, 100) / 100,
    wavelength: clampN(num(grp.wavelength, 60), 10, 300) / 100,
    thickness: clampN(num(grp.thickness, 100), 20, 400) / 100,
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: false,
      depth: false,
    });
    if (!gl) {
      console.error("PredictiveArcSignal: WebGL unavailable");
      return;
    }

    const vs = compile(gl, gl.VERTEX_SHADER, VERT_SRC);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG_SRC);
    if (!vs || !fs) return;
    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error("PredictiveArcSignal link:", gl.getProgramInfoLog(prog));
      return;
    }
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const aPos = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const locs: Record<string, WebGLUniformLocation | null> = {};
    const u = (name: string) => {
      if (!(name in locs)) locs[name] = gl.getUniformLocation(prog, name);
      return locs[name];
    };

    let raf = 0;
    let last = performance.now();
    let clock = 0;
    const PTR_RATE = 6.0;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    const render = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const v = vRef.current;

      clock = (clock + dt * 0.9 * (v.speed as number)) % 6283;

      const ptr = ptrRef.current;
      const k = 1 - Math.exp(-dt * PTR_RATE);
      ptr.x += (ptr.tx - ptr.x) * k;
      ptr.y += (ptr.ty - ptr.y) * k;

      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      const cw = sizeRef.current.w || canvas.clientWidth || 1200;
      const ch = sizeRef.current.h || canvas.clientHeight || 800;
      const bw = Math.max(1, Math.round(cw * dpr));
      const bh = Math.max(1, Math.round(ch * dpr));
      if (canvas.width !== bw || canvas.height !== bh) {
        canvas.width = bw;
        canvas.height = bh;
      }
      gl.viewport(0, 0, bw, bh);

      const pitchCss = Math.min(bw, bh) / dpr / (v.density as number);

      gl.uniform2f(u("uRes"), bw, bh);
      gl.uniform1f(u("uTime"), clock);
      gl.uniform1f(u("uDpr"), dpr);
      gl.uniform1f(u("uCell"), Math.max(2, pitchCss * dpr));
      gl.uniform1f(u("uDot"), pitchCss * 1.2 * (v.dotSize as number));
      gl.uniform1f(u("uA"), v.level as number);
      gl.uniform1f(u("uB"), v.amplitude as number);
      gl.uniform1f(u("uC"), v.wavelength as number);
      gl.uniform1f(u("uD"), v.thickness as number);
      gl.uniform1f(u("uHover"), v.hover as number);
      gl.uniform2f(u("uPtr"), ptr.x * (bw / dpr), ptr.y * (bh / dpr));
      const cg = parseColor(v.bg as string, [0.125, 0.22, 0.29]);
      const cb = parseColor(v.base as string, [0.153, 0.298, 0.404]);
      const ca = parseColor(v.accent as string, [0.173, 0.365, 0.506]);
      const chh = parseColor(v.high as string, [1, 0.435, 0]);
      gl.uniform3f(u("uBg"), cg[0], cg[1], cg[2]);
      gl.uniform3f(u("uBase"), cb[0], cb[1], cb[2]);
      gl.uniform3f(u("uAccent"), ca[0], ca[1], ca[2]);
      gl.uniform3f(u("uHigh"), chh[0], chh[1], chh[2]);

      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!reducedMotion.matches) raf = requestAnimationFrame(render);
    };

    const restart = () => {
      cancelAnimationFrame(raf);
      last = performance.now();
      raf = requestAnimationFrame(render);
    };
    const resizeObserver = new ResizeObserver(() => {
      if (reducedMotion.matches) restart();
    });
    resizeObserver.observe(canvas);
    reducedMotion.addEventListener("change", restart);

    const track = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) return;
      ptrRef.current.tx = clampN((e.clientX - r.left) / r.width, 0, 1);
      ptrRef.current.ty = clampN((e.clientY - r.top) / r.height, 0, 1);
    };
    const onLeave = () => {
      ptrRef.current.tx = 0.5;
      ptrRef.current.ty = 0.5;
    };
    canvas.addEventListener("pointermove", track);
    canvas.addEventListener("pointerenter", track);
    canvas.addEventListener("pointerleave", onLeave);

    raf = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      reducedMotion.removeEventListener("change", restart);
      canvas.removeEventListener("pointermove", track);
      canvas.removeEventListener("pointerenter", track);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        background,
        minWidth: 0,
        minHeight: 0,
        width: typeof width === "number" && width > 0 ? width : "100%",
        height: typeof height === "number" && height > 0 ? height : "100%",
        ...style,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          display: "block",
        }}
      />
    </div>
  );
}

export default PredictiveArcSignal;
