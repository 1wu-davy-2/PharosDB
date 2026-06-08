# PharosDB Login Page — Stitch Design Prompt (v2)

## Context
PharosDB is a database observability platform ("Pharos" = lighthouse in Greek).

---

## Stitch Prompt

```
Design a full-screen immersive login page for "PharosDB", a database observability platform.

**Core Concept:**
The ENTIRE page is a dark ocean scene. A lighthouse stands at the center-bottom, emitting rotating 360-degree light beams across the whole screen. The login form is a floating glass card overlaid on this scene. When the user focuses on an input field, the lighthouse beam animates to point directly at that field — as if the beacon is illuminating the user's path to login.

**Full-Screen Background (fills 100vw × 100vh):**
- Deep ocean gradient background: radial gradient from center-bottom, #0a1628 at edges to #0f2744 at center-bottom where the lighthouse sits
- A minimalist lighthouse SVG/icon at bottom-center of the viewport (about 60px from bottom edge)
- The lighthouse has a glowing amber core (#f59e0b with blur/glow effect)
- Stars/dots scattered across the upper portion of the screen (subtle white dots at varying opacity, simulating a night sky over the ocean)

**The Lighthouse Beam System (CSS-only, the key feature):**
- DEFAULT STATE (no input focus): The lighthouse emits a 360-degree sweeping beam — implemented as a rotating conic-gradient or multiple radial-gradient rays emanating from the lighthouse position. The beam rotates slowly and continuously (one full rotation every 8-10 seconds). The beam color is warm amber/gold with transparency: rgba(245, 158, 11, 0.08) fading to transparent at edges.
- FOCUS STATE (input focused): The rotating beam STOPS its sweep animation and instead snaps to a specific angle pointing toward the focused input field. Use CSS custom properties (--beam-angle) updated via JavaScript on input focus/blur. The beam narrows to a spotlight cone (approx 15-20 degrees wide) pointing at the input. Add a subtle glow around the targeted input when the beam hits it.
- BEAM VISUAL: The beam should be a wedge/pie shape (like a real lighthouse beam) emanating from the lighthouse position. It should have a gradient from brighter at source (rgba(245,158,11,0.15)) to dimmer at edges (rgba(245,158,11,0)). Multiple overlapping beams at slight angle offsets create the "sweeping lighthouse" effect.

**Floating Login Card (centered, over the background):**
- Glassmorphism card: background rgba(15, 26, 46, 0.75) with backdrop-filter: blur(20px)
- Border: 1px solid rgba(245, 158, 11, 0.15)
- Border-radius: 20px
- Max-width: 420px, width: 90%
- Padding: 40px 32px
- Subtle inner glow at the top edge of the card (like the lighthouse beam is catching the top of the card)

**Card Content:**
- Top center: "PharosDB" in text-2xl font-bold text-amber-400, letter-spacing: 0.08em
- Below brand name: a thin amber line (1px, 60px wide, centered, rgba(245,158,11,0.4))
- Below line: "数据库可观测性平台" in text-sm text-gray-400
- Form area (margin-top: 28px):
  - Username field: dark glass input — background rgba(255,255,255,0.05), border rgba(255,255,255,0.12), text-white, placeholder "请输入用户名", rounded-xl, height 50px, padding-left 44px for icon. Focus: border-amber-500/60, box-shadow 0 0 20px rgba(245,158,11,0.15). Icon: subtle user SVG at left.
  - Password field: same style, placeholder "请输入密码", with lock icon left and eye toggle right
  - Gap between fields: 16px
  - Login button: full width, height 50px, background linear-gradient(135deg, #f59e0b, #d97706), text-white font-semibold rounded-xl, text "登 录". Hover: brightness-110, shadow 0 0 30px rgba(245,158,11,0.3). Active: scale(0.98).
  - Loading state: button shows spinner + "登录中…"
- Bottom of card: "© 2026 PharosDB · v0.1.0" in text-xs text-gray-600, centered

**Interactive Beam Mechanics (JavaScript behavior):**
- On page load: beam rotates 360° continuously (CSS animation: rotate 0deg → 360deg, 8s linear infinite)
- On input focus (username OR password): 
  1. Calculate the angle from lighthouse position (bottom-center of viewport) to the center of the focused input
  2. Set CSS custom property --beam-angle on the beam container to that calculated angle
  3. Stop the rotation animation, add a transition to smoothly rotate beam to target angle (0.6s ease-in-out)
  4. Add a subtle amber glow outline around the focused input
  5. Optionally: narrow the beam width (from full 360 sweep to ~20° spotlight)
- On input blur (if no other input is focused):
  1. Resume the 360° rotation animation
  2. Remove the spotlight effect from the input

**Error State:**
- Red-tinted alert inside the card: background rgba(220,38,38,0.1), border rgba(220,38,38,0.3), red text, slide-down animation
- Beam subtly shifts to a reddish tint when error is shown (optional dramatic effect)

**Color Palette:**
- Background: #0a1628, #0f2744, #060f1f (deepest navy)
- Beam: rgba(245, 158, 11, 0.06) to rgba(245, 158, 11, 0.18)
- Card: rgba(15, 26, 46, 0.75)
- Text: #ffffff, #94a3b8 (muted), #f59e0b (accent)
- Input bg: rgba(255,255,255,0.05), border rgba(255,255,255,0.12)
- Error: rgba(220,38,38,0.1)

**Typography:**
- Chinese + English bilingual
- Font: system-ui, -apple-system, "Noto Sans SC"

**Responsive:**
- Below 640px: card width 95%, padding 28px 20px
- Lighthouse icon scales down proportionally
- Beam effect still visible (may be subtler on small screens)

**Accessibility:**
- All inputs have associated labels (visually hidden but screen-reader accessible)
- Focus indicators clearly visible
- Color contrast meets WCAG AA

Generate this as a SINGLE React component file (.jsx) with ALL CSS inline or via a companion CSS module. The lighthouse beam effect MUST be implemented with CSS + minimal JavaScript (no canvas, no external libraries). Include the beam angle calculation logic in the component.
```
