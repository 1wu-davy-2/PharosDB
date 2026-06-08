# PharosDB Dashboard Layout — Stitch Design Prompt

## Context
After login, users land on the main dashboard. This is the monitoring command center for DBAs managing database clusters. It needs to feel powerful, data-dense but organized, with a professional operations-center aesthetic.

---

## Stitch Prompt

```
Design the main dashboard layout for "PharosDB", a database observability platform used by DBAs and SREs.

**Layout Structure:**
- Full application shell with: collapsible sidebar navigation (left) + top header bar + main content area
- Sidebar: 240px wide when expanded, 64px when collapsed (icon-only mode)
- Top header: 56px height, spans full width to the right of sidebar
- Main content: fills remaining space, scrollable

**Sidebar Navigation (dark theme):**
- Background: deep navy #0f1a2e
- Top area: PharosDB logo mark (a small lighthouse beam icon in amber) + "PharosDB" text in white, 24px height area with padding
- Navigation items with icons (use simple SVG icons or emoji):
  - 📊 监控总览 (Overview Dashboard) — default active
  - 🔍 SQL 分析 (SQL Analytics)
  - 🔗 锁等待拓扑 (Lock Topology)
  - ⚙️ 实例管理 (Instance Management)
  - 📋 诊断报告 (Diagnostic Reports)
  - ⚙️ 系统设置 (System Settings) — at the bottom, separated by a divider
- Each nav item: height 44px, left border 3px transparent by default, left border amber-500 when active, subtle bg change on hover
- Active item: bg rgba(245, 158, 11, 0.1), text-amber-400
- Inactive items: text-gray-400, hover:text-gray-200
- Icons: 20x20 area on the left, text beside it, font-size: 14px
- Collapse toggle: small chevron button at the bottom of sidebar
- When collapsed: only icons shown, tooltip on hover for item name

**Top Header Bar:**
- Background: white #ffffff, bottom border 1px #e2e8f0
- Left area: hamburger/expand button for sidebar toggle
- Center: breadcrumb or page title area
- Right area (flex items with 16px gap):
  - A notification bell icon with a small red dot badge
  - User avatar circle (amber background with user initials) + username text
  - Dropdown on avatar click: "个人设置" / "退出登录" with hover states

**Main Content Area (Dashboard Overview):**
- Background: #f1f5f9 (slate-50)
- Padding: 24px
- Top row: 4 stat cards in a grid (4 columns on desktop, 2 on tablet, 1 on mobile)
  - Each card: white bg, rounded-xl, shadow-sm, padding 20px
  - Inside: small muted label text at top, large bold number in middle, subtle trend indicator (green up / red down arrow + percentage) at bottom
  - Stat examples: "活跃实例 42", "今日慢查询 1,247", "平均响应时间 23ms", "告警 3"
- Second row: 2-column grid
  - Left: larger card "数据库健康概览" — a placeholder for a chart/diagram area with a subtle grid pattern background, height 320px
  - Right: card "最近告警" (Recent Alerts) — a compact list of 5 recent alert items, each with severity dot (red/yellow), timestamp, and brief message, separated by subtle dividers
- Third row: full-width card "Top 10 慢查询" — a simple table with columns: 排名, SQL指纹, 平均耗时, 执行次数, 趋势
- All cards have a header row with title on left and a "查看全部 →" link on right in muted text

**Color Palette:**
- Sidebar: #0f1a2e (bg), #1a2740 (hover), #f59e0b (accent)
- Header: #ffffff, border #e2e8f0
- Content bg: #f1f5f9
- Cards: #ffffff, shadow-sm
- Text: #1e293b (primary), #64748b (secondary), #94a3b8 (muted)
- Amber: #f59e0b, #d97706 (primary accent)
- Status colors: #22c55e (healthy), #ef4444 (critical), #f59e0b (warning)

**Typography:**
- Chinese + English bilingual
- Font: system-ui, "Noto Sans SC"
- Card stat numbers: text-2xl font-bold
- Labels: text-xs text-gray-500 uppercase tracking-wide
- Body text: text-sm

**Interactions:**
- Sidebar collapse: smooth 200ms transition on width, text fades out when collapsing
- Nav items: smooth background color transition
- Cards: subtle hover lift effect (translateY(-2px) + shadow increase)
- Table rows: hover bg-slate-50

**Responsive:**
- Below 1024px: sidebar becomes overlay/modal style
- Below 768px: cards stack to 1 column, table becomes horizontally scrollable

Generate this as a React component shell/layout with Tailwind CSS classes. Include the sidebar, header, and placeholder cards. Make the layout functional (sidebar collapse, active nav state, avatar dropdown).
```
