# PharosDB UI Design Prompts

用于 [Google Stitch](https://stitch.withgoogle.com/) 生成 UI 的提示词。

## 使用方法

1. 打开 https://stitch.withgoogle.com/
2. 复制对应 `.md` 文件中 ` ``` ` 代码块内的 Stitch Prompt 英文文本
3. 粘贴到 Stitch 中生成 UI
4. 将 Stitch 生成的代码导出为 React 组件，放入 `frontend/src/pages/` 目录

## 设计页面列表

| 文件 | 页面 | 说明 |
|------|------|------|
| `01_login_page.md` | 登录页 | 灯塔光束主题，左右分栏布局 |
| `02_dashboard_layout.md` | 仪表盘布局 | 侧边栏 + 顶栏 + 数据卡片 |

## 设计系统

| 属性 | 值 |
|------|-----|
| 主色 | Amber/Gold `#f59e0b` — 灯塔之光 |
| 深色 | Navy `#0f1a2e` — 深海夜空 |
| 浅色背景 | Slate `#f1f5f9` / 卡片白 `#ffffff` |
| 字体 | system-ui, "Noto Sans SC" |
| 语言 | 中英双语 |
| CSS 框架 | Tailwind CSS |
| 框架 | React 18 |
