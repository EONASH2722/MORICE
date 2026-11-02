import { useEffect, useRef, useState } from "react";

const vertexSource = `
attribute vec2 position;
varying vec2 uv;
void main() { uv = position * 0.5 + 0.5; gl_Position = vec4(position, 0.0, 1.0); }
`;
// Interactive MORICE animation, rendered locally without external assets or runtimes.
const fragmentSource = `
precision mediump float;
varying vec2 uv;
uniform vec2 resolution;
uniform vec2 pointer;
uniform float time;
uniform sampler2D wordmark;
void main() {
  float aspect = resolution.x / resolution.y;
  vec2 p = (uv - 0.5) * vec2(aspect, 1.0) - pointer * vec2(0.018, 0.012);
  float d = length(p);
  float angle = atan(p.y, p.x);
  float light = pow(max(0.0, cos(angle - 0.95 - sin(time * 0.12) * 0.3)), 5.0);
  float edge = abs(d - 0.275);
  float rim = exp(-edge * 250.0) * (0.12 + light * 1.8);
  float halo = exp(-edge * 54.0) * (0.018 + light * 0.5);
  float atmosphere = exp(-edge * 14.0) * light * 0.065;
  float lens = exp(-d * 7.5);
  vec2 textUv = uv;
  textUv.x += p.x * lens * 1.35;
  textUv.y = 0.5 + (uv.y - 0.5) * (1.0 + lens * 2.3);
  textUv.x = fract((textUv.x - 0.5) * aspect * 0.48 + 0.5 - time * 0.027);
  float aberration = 0.002 + lens * 0.005;
  vec3 letters;
  letters.r = texture2D(wordmark, textUv + vec2(aberration, 0.0)).r;
  letters.g = texture2D(wordmark, textUv).g;
  letters.b = texture2D(wordmark, textUv - vec2(aberration, 0.0)).b;
  letters *= (0.26 + smoothstep(0.13, 0.32, d) * 0.30) * (0.88 + 0.12 * sin(uv.y * resolution.y * 2.1));
  vec3 color = letters + vec3(0.70, 0.55, 1.0) * (rim + halo) + vec3(0.45, 0.25, 0.8) * atmosphere;
  gl_FragColor = vec4(color * (1.0 - smoothstep(0.35, 0.72, abs(uv.y - 0.5))), 1.0);
}
`;

export default function HeroScene({ motion }: { motion: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const motionRef = useRef(motion);
  const renderRef = useRef<(() => void) | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    motionRef.current = motion;
    renderRef.current?.();
  }, [motion]);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: false,
      powerPreference: "low-power",
    });
    if (!gl) return;
    const shaders: WebGLShader[] = [];
    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      shaders.push(shader);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
    };
    const vertex = compile(gl.VERTEX_SHADER, vertexSource),
      fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
    const program = gl.createProgram(),
      buffer = gl.createBuffer(),
      texture = gl.createTexture();
    const release = () => {
      shaders.forEach((shader) => gl.deleteShader(shader));
      gl.deleteProgram(program);
      gl.deleteBuffer(buffer);
      gl.deleteTexture(texture);
    };
    if (!vertex || !fragment || !program || !buffer || !texture) {
      release();
      return;
    }
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      release();
      return;
    }
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const position = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const resolutionLocation = gl.getUniformLocation(program, "resolution"),
      pointerLocation = gl.getUniformLocation(program, "pointer"),
      timeLocation = gl.getUniformLocation(program, "time");
    gl.uniform1i(gl.getUniformLocation(program, "wordmark"), 0);
    let disposed = false,
      inView = true,
      frame = 0,
      elapsed = 0,
      previous = 0,
      textureReady = false;
    let pointerX = 0,
      pointerY = 0,
      currentX = 0,
      currentY = 0;
    const draw = (now: number) => {
      frame = 0;
      if (disposed || !textureReady || gl.isContextLost()) return;
      const running = motionRef.current && inView && !document.hidden;
      if (running && previous) elapsed += Math.min(now - previous, 60) / 1000;
      previous = running ? now : 0;
      currentX += (pointerX - currentX) * 0.045;
      currentY += (pointerY - currentY) * 0.045;
      gl.uniform2f(resolutionLocation, canvas.width, canvas.height);
      gl.uniform2f(
        pointerLocation,
        motionRef.current ? currentX : 0,
        motionRef.current ? currentY : 0,
      );
      gl.uniform1f(timeLocation, elapsed);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      if (running) frame = requestAnimationFrame(draw);
    };
    const requestDraw = () => {
      if (disposed) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    };
    renderRef.current = requestDraw;
    const resize = () => {
      const bounds = canvas.getBoundingClientRect(),
        dpr = Math.min(devicePixelRatio || 1, innerWidth < 680 ? 1.25 : 1.6);
      canvas.width = Math.round(bounds.width * dpr);
      canvas.height = Math.round(bounds.height * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      requestDraw();
    };
    const createWordmark = () => {
      if (disposed || gl.isContextLost()) return;
      const image = document.createElement("canvas");
      image.width = 2048;
      image.height = 512;
      const ctx = image.getContext("2d");
      if (!ctx) return;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, image.width, image.height);
      ctx.fillStyle = "#fff";
      ctx.font = '600 205px "M PLUS 1", sans-serif';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.translate(1024, 256);
      ctx.scale(1.8, 1);
      ctx.fillText("MORICE", 0, 0);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        image,
      );
      textureReady = true;
      setReady(true);
      resize();
    };
    const pointerMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      const bounds = canvas.getBoundingClientRect();
      pointerX = (event.clientX - bounds.left) / bounds.width - 0.5;
      pointerY = 0.5 - (event.clientY - bounds.top) / bounds.height;
    };
    const contextLost = (event: Event) => {
      event.preventDefault();
      setReady(false);
      cancelAnimationFrame(frame);
    };
    const observer = new IntersectionObserver((entries) => {
      inView = entries[0]?.isIntersecting ?? false;
      previous = 0;
      requestDraw();
    });
    observer.observe(canvas);
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    canvas.addEventListener("pointermove", pointerMove, { passive: true });
    canvas.addEventListener("webglcontextlost", contextLost);
    document.addEventListener("visibilitychange", requestDraw);
    document.fonts
      .load('600 205px "M PLUS 1"')
      .then(createWordmark)
      .catch(createWordmark);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      resizeObserver.disconnect();
      renderRef.current = null;
      canvas.removeEventListener("pointermove", pointerMove);
      canvas.removeEventListener("webglcontextlost", contextLost);
      document.removeEventListener("visibilitychange", requestDraw);
      release();
    };
  }, []);
  return (
    <canvas
      ref={canvasRef}
      className={`hero-canvas ${ready ? "is-ready" : ""}`}
      aria-hidden="true"
    />
  );
}
