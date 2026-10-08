# glowmark ✨

Turn Markdown into a beautiful, standalone HTML page. One task, done well.

```
glowmark README.md
```

## Install

```bash
cd glowmark
pip install -e .
```

Dependencies: `markdown`, `pygments` (optional: `watchdog` for live reload).

## Usage

```bash
glowmark doc.md                  # render + open in browser
glowmark --serve doc.md          # live-reload preview server (port 7654)
glowmark --web                   # paste markdown in a browser editor, live preview
glowmark --web notes.md          # same, pre-loaded with a file
glowmark doc.md --out page.html  # write a shareable standalone file
cat notes.md | glowmark - --out notes.html
glowmark doc.md --theme dark --title "My Doc"
glowmark doc.md --port 8080 --no-open
```

## Features

- **Standalone output** — CSS and syntax highlighting fully inlined, works offline
- **Live preview** — `--serve` watches the file and reloads the browser via SSE
- **Web editor** — `--web` opens a paste-in browser editor with instant server-side rendering, copy-HTML and download buttons
- **Landing page** — `site/index.html` includes a fully client-side live markdown demo (no install needed)
- **Scroll-spy TOC** — sidebar with active-section highlighting
- **Themes** — `auto` / `light` / `dark`, toggle persisted in localStorage
- **GFM extras** — tables, task lists, footnotes, fenced code
- **GitHub alerts** — `> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`, `> [!IMPORTANT]`
- **Front matter** — `title`, `author`, `date`, `description` → hero header
- **Stats** — word count + reading time computed automatically
- **Copy buttons** on every code block
- **Math** (KaTeX) and **mermaid diagrams** load automatically when detected
- **Print styles** — the page prints/exports to PDF cleanly

## Try the demo

```bash
glowmark --serve examples/demo.md
```
