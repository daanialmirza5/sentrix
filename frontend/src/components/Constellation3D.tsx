import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

export type Node3D = { id: string; label: string; role: string; version: number | null };

const ROLE_COLOR: Record<string, number> = { procurement: 0x22d3ee, orchestrator: 0xa78bfa, support: 0x34d399, hr: 0xf472b6 };
const colorFor = (role: string) => ROLE_COLOR[role] ?? 0xfbbf24;

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}

/**
 * Agents orbit the SENTRIX gateway core, each bound by a link (its signed Role Contract).
 * Pure three.js; renders only while visible; disposes everything on unmount.
 */
export default function Constellation3D({ nodes, onSelect, height = 420, decorative = false }:
  { nodes: Node3D[]; onSelect?: (id: string) => void; height?: number; decorative?: boolean }) {
  const mount = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ node: Node3D; x: number; y: number } | null>(null);
  const [fallback, setFallback] = useState(false);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    if (!webglAvailable()) { setFallback(true); return; }
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070d, 0.035);
    const camera = new THREE.PerspectiveCamera(45, el.clientWidth / height, 0.1, 200);
    camera.position.set(0, 6.5, 17);
    camera.lookAt(0, 0, 0);
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    } catch { setFallback(true); return; }
    // The decorative backdrop sits under a gradient; 1x is visually identical and much cheaper on weak GPUs.
    renderer.setPixelRatio(decorative ? 1 : Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, height);
    renderer.domElement.setAttribute("aria-hidden", "true");
    el.appendChild(renderer.domElement);

    const world = new THREE.Group();
    scene.add(world);

    // --- core: glowing sphere + wireframe shell + halo sprite
    const core = new THREE.Mesh(new THREE.SphereGeometry(1.15, 48, 48),
      new THREE.MeshBasicMaterial({ color: 0x22d3ee }));
    const shell = new THREE.Mesh(new THREE.IcosahedronGeometry(1.9, 1),
      new THREE.MeshBasicMaterial({ color: 0x67e8f9, wireframe: true, transparent: true, opacity: 0.35 }));
    const haloTex = (() => {
      const c = document.createElement("canvas"); c.width = c.height = 128;
      const g = c.getContext("2d")!;
      const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      grd.addColorStop(0, "rgba(103,232,249,0.9)"); grd.addColorStop(0.35, "rgba(34,211,238,0.35)"); grd.addColorStop(1, "rgba(34,211,238,0)");
      g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
      return new THREE.CanvasTexture(c);
    })();
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    halo.scale.set(7, 7, 1);
    world.add(core, shell, halo);

    // --- starfield
    const starGeo = new THREE.BufferGeometry();
    const starPos = new Float32Array(900 * 3);
    for (let i = 0; i < 900; i++) {
      const r = 35 + Math.random() * 45, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
      starPos.set([r * Math.sin(ph) * Math.cos(th), r * Math.cos(ph), r * Math.sin(ph) * Math.sin(th)], i * 3);
    }
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0x8aa0c8, size: 0.12, transparent: true, opacity: 0.7 }));
    scene.add(stars);

    // --- agents on tilted orbits with contract links and travelling pulses
    const list = nodes.length ? nodes : [];
    type A = { node: Node3D; mesh: THREE.Mesh; glow: THREE.Sprite; line: THREE.Line; pulse: THREE.Mesh; radius: number; speed: number; phase: number; tilt: number; ring: THREE.Mesh };
    const agents: A[] = list.map((node, i) => {
      const color = colorFor(node.role);
      const radius = 4.2 + (i % 3) * 1.6;
      const tilt = ((i * 37) % 60 - 30) * (Math.PI / 180);
      const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.012, 6, 160),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.18 }));
      ring.rotation.x = Math.PI / 2 + tilt;
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.34, 24, 24), new THREE.MeshBasicMaterial({ color }));
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTex, color, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      glow.scale.set(2.2, 2.2, 1);
      const lineGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
      const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color, transparent: true, opacity: node.version ? 0.55 : 0.15 }));
      const pulse = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
      mesh.userData.node = node;
      world.add(ring, line, mesh, glow, pulse);
      return { node, mesh, glow, line, pulse, radius, speed: 0.12 + (i % 4) * 0.035, phase: (i / Math.max(1, list.length)) * Math.PI * 2, tilt, ring };
    });

    const ray = new THREE.Raycaster();
    const mouse = new THREE.Vector2(-9, -9);
    let hovered: A | null = null;
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    };
    const onLeave = () => { mouse.set(-9, -9); };
    const onClick = () => { if (hovered && selectRef.current && !decorative) selectRef.current(hovered.node.id); };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    renderer.domElement.addEventListener("click", onClick);

    const onResize = () => {
      const w = el.clientWidth;
      camera.aspect = w / height; camera.updateProjectionMatrix(); renderer.setSize(w, height);
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(el);

    let visible = true;
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(el);

    const clock = new THREE.Clock();
    let raf = 0;
    const tmp = new THREE.Vector3();
    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const t = reduced ? 0 : clock.getElapsedTime();
      world.rotation.y = t * 0.05;
      shell.rotation.x = t * 0.15; shell.rotation.y = t * 0.1;
      halo.scale.setScalar(6.6 + Math.sin(t * 1.6) * 0.4);
      stars.rotation.y = -t * 0.008;
      for (const a of agents) {
        const ang = a.phase + t * a.speed;
        a.mesh.position.set(Math.cos(ang) * a.radius, Math.sin(ang) * a.radius * Math.sin(a.tilt), Math.sin(ang) * a.radius * Math.cos(a.tilt));
        a.glow.position.copy(a.mesh.position);
        const pos = a.line.geometry.attributes.position as THREE.BufferAttribute;
        pos.setXYZ(1, a.mesh.position.x, a.mesh.position.y, a.mesh.position.z); pos.needsUpdate = true;
        const k = (t * 0.6 + a.phase) % 1;
        a.pulse.position.copy(a.mesh.position).multiplyScalar(1 - k);
        a.pulse.visible = !!a.node.version;
      }
      ray.setFromCamera(mouse, camera);
      const hit = ray.intersectObjects(agents.map((a) => a.mesh))[0];
      const next = hit ? agents.find((a) => a.mesh === hit.object) ?? null : null;
      if (next !== hovered) {
        if (hovered) { hovered.mesh.scale.setScalar(1); hovered.glow.scale.set(2.2, 2.2, 1); }
        hovered = next;
        renderer.domElement.style.cursor = next && !decorative ? "pointer" : "default";
        if (!next) setHover(null);
      }
      if (hovered) {
        hovered.mesh.scale.setScalar(1.5); hovered.glow.scale.set(3.4, 3.4, 1);
        tmp.copy(hovered.mesh.position).applyMatrix4(world.matrixWorld).project(camera);
        const node = hovered.node;
        const x = (tmp.x * 0.5 + 0.5) * el.clientWidth, y = (-tmp.y * 0.5 + 0.5) * height;
        setHover((h) => (h && h.node.id === node.id && Math.abs(h.x - x) < 2 && Math.abs(h.y - y) < 2 ? h : { node, x, y }));
      }
      renderer.render(scene, camera);
    };
    frame();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect(); io.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      renderer.domElement.removeEventListener("click", onClick);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => x.dispose());
      });
      haloTex.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [nodes, height, decorative]);

  if (fallback) {
    return (
      <div className="relative flex items-center justify-center" style={{ height }} role="img" aria-label="Agent constellation (2D fallback)">
        <div className="absolute h-24 w-24 rounded-full bg-cyan-400/30 blur-2xl" />
        <div className="relative grid h-16 w-16 place-items-center rounded-full bg-cyan-400 text-xs font-bold text-ink-950">SENTRIX</div>
        {nodes.map((n, i) => {
          const a = (i / Math.max(1, nodes.length)) * Math.PI * 2;
          return <span key={n.id} className="absolute rounded-full border border-white/10 bg-ink-900 px-2 py-0.5 text-[11px] text-ink-300"
            style={{ transform: `translate(${Math.cos(a) * 140}px, ${Math.sin(a) * 110}px)` }}>{n.label}</span>;
        })}
      </div>
    );
  }

  return (
    <div className="relative" style={{ height }} role="img" aria-label={`3D constellation of ${nodes.length} agents watched by the SENTRIX gateway`}>
      <div ref={mount} className="absolute inset-0" />
      {hover && !decorative && (
        <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[130%] animate-fade-in rounded-xl border border-white/10 bg-ink-950/90 px-3 py-2 text-xs shadow-xl backdrop-blur"
          style={{ left: hover.x, top: hover.y }}>
          <div className="font-semibold text-ink-100">{hover.node.label}</div>
          <div className="font-mono text-[11px] text-ink-500">{hover.node.id}</div>
          <div className="mt-1 text-ink-300">{hover.node.role} · {hover.node.version ? `contract v${hover.node.version} (signed)` : "no contract"}</div>
          <div className="mt-1 text-cyan-300">Click to open contract</div>
        </div>)}
    </div>
  );
}
