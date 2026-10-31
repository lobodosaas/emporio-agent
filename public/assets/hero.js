// Hero scene: a procedural acoustic guitar drawn with Three.js.
// Click (or Enter on the canvas) strums the strings: they vibrate and a
// Karplus-Strong synth plays an E major chord. No audio before a gesture.
import * as THREE from "three";

const stage = document.querySelector("[data-guitar]");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function supportsWebGL() {
  try { return !!document.createElement("canvas").getContext("webgl2"); } catch { return false; }
}

if (stage && supportsWebGL()) init();
else if (stage) stage.querySelector(".stage-fallback")?.removeAttribute("hidden");

function bodyShape() {
  // Half-width of the body along its length (y from -1 at the tail to 1 at the neck joint):
  // two bouts joined by a smooth maximum, so the waist curves in without corners.
  const lower = (y) => { const d = (y + 0.42) / 0.58; return d * d < 1 ? 0.92 * Math.sqrt(1 - d * d) : 0; };
  const upper = (y) => { const d = (y - 0.46) / 0.54; return d * d < 1 ? 0.72 * Math.sqrt(1 - d * d) : 0; };
  const K = 14;
  const half = (y) => {
    const a = lower(y), b = upper(y);
    if (a === 0 && b === 0) return 0;
    const m = Math.max(a, b);
    return Math.max(0, m + Math.log(Math.exp(K * (a - m)) + Math.exp(K * (b - m))) / K - Math.log(2) / K);
  };
  const pts = [];
  const N = 90;
  for (let i = 0; i <= N; i++) { const y = -1 + (2 * i) / N; pts.push(new THREE.Vector2(half(y), y)); }
  for (let i = N; i >= 0; i--) { const y = -1 + (2 * i) / N; pts.push(new THREE.Vector2(-half(y), y)); }
  const shape = new THREE.Shape(pts);
  const hole = new THREE.Path();
  hole.absarc(0, 0.28, 0.2, 0, Math.PI * 2, true);
  shape.holes.push(hole);
  return shape;
}

// Spruce top: straight, tight vertical grain painted once on a canvas.
function spruceGrain() {
  const c = document.createElement("canvas");
  c.width = 512; c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = "#e4bc82";
  g.fillRect(0, 0, 512, 512);
  let x = 0;
  while (x < 512) {
    const w = 1 + Math.random() * 2.2;
    g.fillStyle = `rgba(150, 98, 45, ${0.10 + Math.random() * 0.16})`;
    g.beginPath();
    for (let y = 0; y <= 512; y += 32) g.lineTo(x + Math.sin(y / 90 + x) * 1.5, y);
    for (let y = 512; y >= 0; y -= 32) g.lineTo(x + w + Math.sin(y / 90 + x) * 1.5, y);
    g.fill();
    x += 4 + Math.random() * 7;
  }
  const texture = new THREE.CanvasTexture(c);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(0.55, 0.55); // extrude UVs are in body units (-1..1)
  texture.anisotropy = 4;
  return texture;
}

function init() {
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "Violão em 3D. Clique para ouvir um acorde de Mi maior.");
  canvas.tabIndex = 0;
  stage.prepend(canvas);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50);
  camera.position.set(0, 0, 9.2);

  scene.add(new THREE.HemisphereLight(0xffffff, 0xc9d6e2, 1.4));
  const key = new THREE.DirectionalLight(0xfff1dd, 2.6);
  key.position.set(3, 4, 5);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9cc8ec, 1.2);
  rim.position.set(-4, 2, -3);
  scene.add(rim);

  const guitar = new THREE.Group();
  scene.add(guitar);

  // Body: spruce top, rosewood sides.
  const spruce = new THREE.MeshStandardMaterial({ map: spruceGrain(), roughness: 0.42 });
  const rosewood = new THREE.MeshStandardMaterial({ color: 0x5a2e1b, roughness: 0.55 });
  const ebony = new THREE.MeshStandardMaterial({ color: 0x1c1410, roughness: 0.5 });
  const metal = new THREE.MeshStandardMaterial({ color: 0xd8d8d8, metalness: 0.9, roughness: 0.25 });

  const depth = 0.32;
  const bodyGeo = new THREE.ExtrudeGeometry(bodyShape(), {
    depth, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 3, curveSegments: 64,
  });
  bodyGeo.translate(0, 0, -depth / 2);
  const body = new THREE.Mesh(bodyGeo, [spruce, rosewood]);
  guitar.add(body);

  const front = depth / 2 + 0.031;
  const cavity = new THREE.Mesh(new THREE.CircleGeometry(0.2, 48), new THREE.MeshBasicMaterial({ color: 0x120b07 }));
  cavity.position.set(0, 0.28, -depth / 2 + 0.02);
  guitar.add(cavity);
  const rosette = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.27, 64), new THREE.MeshStandardMaterial({ color: 0x7a3f1d, roughness: 0.4 }));
  rosette.position.set(0, 0.28, front + 0.001);
  guitar.add(rosette);
  const rosetteInlay = new THREE.Mesh(new THREE.RingGeometry(0.235, 0.245, 64), new THREE.MeshStandardMaterial({ color: 0xf39c12, roughness: 0.3 }));
  rosetteInlay.position.set(0, 0.28, front + 0.002);
  guitar.add(rosetteInlay);

  const bridge = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.11, 0.05), ebony);
  bridge.position.set(0, -0.5, front + 0.02);
  guitar.add(bridge);

  // Neck, fretboard, frets, headstock, tuners.
  const neckLen = 2.15;
  const neck = new THREE.Mesh(new THREE.BoxGeometry(0.24, neckLen, 0.16), rosewood);
  neck.position.set(0, 0.95 + neckLen / 2, -0.02);
  guitar.add(neck);
  const board = new THREE.Mesh(new THREE.BoxGeometry(0.26, neckLen + 0.25, 0.04), ebony);
  board.position.set(0, 0.95 + neckLen / 2 - 0.12, 0.08 + 0.02);
  guitar.add(board);
  const nutY = 0.95 + neckLen;
  const scaleLength = nutY - -0.5; // nut to bridge saddle
  for (let i = 1; i <= 19; i++) {
    const y = nutY - scaleLength * (1 - Math.pow(2, -i / 12)); // real fret spacing, 12th fret at mid-scale
    if (y < 0.85) break;
    const fret = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.012, 0.012), metal);
    fret.position.set(0, y, 0.125);
    guitar.add(fret);
  }
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.6, 0.06), rosewood);
  head.position.set(0, nutY + 0.32, 0.02);
  head.rotation.x = -0.18;
  guitar.add(head);
  for (let i = 0; i < 6; i++) {
    const side = i < 3 ? -1 : 1;
    const peg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.16, 12), metal);
    peg.rotation.z = Math.PI / 2;
    peg.position.set(side * 0.24, nutY + 0.15 + (i % 3) * 0.16, 0.04);
    guitar.add(peg);
  }

  // Strings as polylines so they can vibrate.
  const SEG = 48;
  const bottom = -0.5;
  const strings = [];
  for (let i = 0; i < 6; i++) {
    const xBridge = -0.2 + i * 0.08;
    const xNut = -0.1 + i * 0.04;
    const positions = new Float32Array((SEG + 1) * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.LineBasicMaterial({ color: i < 3 ? 0xb08d57 : 0xe6e6e6 });
    const line = new THREE.Line(geo, mat);
    guitar.add(line);
    strings.push({ line, positions, xBridge, xNut, amp: 0, phase: 0, freq: 9 + i * 1.6 });
  }
  function layoutStrings(time) {
    for (const s of strings) {
      for (let j = 0; j <= SEG; j++) {
        const t = j / SEG;
        const envelope = Math.sin(Math.PI * t);
        const wobble = s.amp * envelope * Math.sin(time * s.freq * 6 + s.phase);
        s.positions[j * 3] = s.xBridge + (s.xNut - s.xBridge) * t + wobble;
        s.positions[j * 3 + 1] = bottom + (nutY - bottom) * t;
        s.positions[j * 3 + 2] = front + 0.06 - 0.02 * t;
      }
      s.line.geometry.attributes.position.needsUpdate = true;
    }
  }
  layoutStrings(0);

  guitar.position.y = -1.15; // guitar spans y -1..3.6; centre it in frame
  guitar.rotation.z = -0.32;

  // ---------- Karplus-Strong pluck ----------
  let audio;
  function pluck(freq, when) {
    const ctx = audio;
    const sr = ctx.sampleRate;
    const length = Math.floor(sr * 2.2);
    const buffer = ctx.createBuffer(1, length, sr);
    const data = buffer.getChannelData(0);
    const period = Math.floor(sr / freq);
    const ring = new Float32Array(period).map(() => Math.random() * 2 - 1);
    for (let i = 0; i < length; i++) {
      const k = i % period;
      const next = (k + 1) % period;
      data[i] = ring[k];
      ring[k] = 0.996 * 0.5 * (ring[k] + ring[next]);
    }
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    const gain = ctx.createGain();
    gain.gain.value = 0.18;
    src.connect(gain).connect(ctx.destination);
    src.start(when);
  }
  function strum() {
    try {
      audio = audio || new AudioContext();
      const now = audio.currentTime + 0.02;
      // E major, open position: E2 B2 E3 G#3 B3 E4
      [82.41, 123.47, 164.81, 207.65, 246.94, 329.63].forEach((f, i) => pluck(f, now + i * 0.035));
    } catch { /* audio unavailable: strings still move */ }
    strings.forEach((s, i) => setTimeout(() => { s.amp = 0.045; s.phase = Math.random() * 6; }, i * 35));
  }
  canvas.addEventListener("click", strum);
  canvas.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); strum(); } });

  // ---------- sizing, pointer, loop ----------
  function resize() {
    const { width, height } = stage.getBoundingClientRect();
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.position.z = width < 520 ? 10.4 : 9.2;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage);
  resize();

  const pointer = { x: 0, y: 0 };
  stage.addEventListener("pointermove", (e) => {
    const r = stage.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1;
  });

  let visible = true;
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }).observe(stage);

  const clock = new THREE.Clock();
  let intro = reduceMotion ? 1 : 0;
  function frame() {
    requestAnimationFrame(frame);
    if (!visible) return;
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;
    intro = Math.min(1, intro + dt * 0.7);
    const ease = 1 - Math.pow(1 - intro, 4);
    const sway = reduceMotion ? 0 : Math.sin(t * 0.35) * 0.45;
    guitar.rotation.y += ((-0.9 + ease * 0.9 + sway + pointer.x * 0.25) - guitar.rotation.y) * 0.06;
    guitar.rotation.x += ((pointer.y * 0.12) - guitar.rotation.x) * 0.06;
    for (const s of strings) s.amp *= Math.pow(0.04, dt);
    layoutStrings(t);
    renderer.render(scene, camera);
  }
  frame();
}
