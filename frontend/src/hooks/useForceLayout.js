import { useCallback, useRef } from "react";

// ─── tiny force simulation (no d3 dependency) ────────────────────────────────
// Shared by DashboardPage (lock radar) and LockPage (lock topology)

export default function useForceLayout(nodes, edges, width, height) {
  const posRef = useRef({});

  const getPos = useCallback(() => {
    const positions = {};
    const n = nodes.length;
    if (n === 0) return positions;

    nodes.forEach((node, i) => {
      if (posRef.current[node.trx_id]) {
        positions[node.trx_id] = { ...posRef.current[node.trx_id] };
      } else {
        const angle = (2 * Math.PI * i) / n;
        const r = Math.min(width, height) * 0.32;
        positions[node.trx_id] = {
          x: width / 2 + r * Math.cos(angle),
          y: height / 2 + r * Math.sin(angle),
          vx: 0,
          vy: 0,
        };
      }
    });

    // run ~120 ticks of force simulation
    const REPULSION = 4000;
    const SPRING_LEN = 160;
    const SPRING_K = 0.04;
    const DAMPING = 0.8;
    const CENTER_K = 0.01;
    const ids = Object.keys(positions);

    for (let tick = 0; tick < 120; tick++) {
      // repulsion between all pairs
      for (let a = 0; a < ids.length; a++) {
        for (let b = a + 1; b < ids.length; b++) {
          const pa = positions[ids[a]];
          const pb = positions[ids[b]];
          let dx = pb.x - pa.x;
          let dy = pb.y - pa.y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = REPULSION / (dist * dist);
          dx /= dist; dy /= dist;
          pa.vx -= force * dx; pa.vy -= force * dy;
          pb.vx += force * dx; pb.vy += force * dy;
        }
      }
      // spring attraction along edges
      for (const edge of edges) {
        const ps = positions[edge.source];
        const pt = positions[edge.target];
        if (!ps || !pt) continue;
        let dx = pt.x - ps.x;
        let dy = pt.y - ps.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = SPRING_K * (dist - SPRING_LEN);
        dx /= dist; dy /= dist;
        ps.vx += force * dx; ps.vy += force * dy;
        pt.vx -= force * dx; pt.vy -= force * dy;
      }
      // gravity toward center
      for (const id of ids) {
        const p = positions[id];
        p.vx += (width / 2 - p.x) * CENTER_K;
        p.vy += (height / 2 - p.y) * CENTER_K;
        p.vx *= DAMPING; p.vy *= DAMPING;
        p.x += p.vx; p.y += p.vy;
        // clamp
        p.x = Math.max(60, Math.min(width - 60, p.x));
        p.y = Math.max(60, Math.min(height - 60, p.y));
      }
    }

    posRef.current = positions;
    return positions;
  }, [nodes, edges, width, height]);

  return getPos;
}

// ─── node colour by type ──────────────────────────────────────────────────────

export const NODE_COLORS = {
  blocker:  { fill: "#ef4444", stroke: "#b91c1c" },
  waiter:   { fill: "#f97316", stroke: "#c2410c" },
  both:     { fill: "#a855f7", stroke: "#7e22ce" },
  deadlock: { fill: "#eab308", stroke: "#a16207" },
};
