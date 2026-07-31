# OpenAlgo Fleet Manager — Design System

Source of truth: `Design/Fleet Manager Design System.dc.html` (the design doc) → this file
(the written spec) → `static/style.css` (the implementation) → `static/preview.html` (a live
gallery of every class, no auth, no data). Change the design doc first, then keep the other
three in step.

## Product Context

Multi-server orchestration dashboard for OpenAlgo trading instances. Operations teams monitor server health, manage deployments, and provision new instances across a fleet of trading servers. This is serious infrastructure tooling — needs to communicate reliability, signal density, and operational clarity at a glance.

## Memorable Thing

**"Serious tooling for serious money."** This dashboard manages live trading infrastructure. Every pixel should communicate that this is production-grade software handling real financial operations. Clean, dense, authoritative.

## Aesthetic Direction

**Modern technical dashboard** — inspired by Datadog, Grafana, and Vercel. Dark-first with high information density, subtle depth, and precise typography. The aesthetic says "this is professional infrastructure software" without needing to announce it.

- Decoration level: Minimal — every visual element earns its place
- Layout: Fixed sidebar nav (desktop), card-based content areas, data tables as primary interaction pattern
- Density: Comfortable but not sparse — operations teams need to see many servers at once

## Typography

| Role | Font | Weight | Rationale |
|------|------|--------|-----------|
| Primary UI | Inter | 400/500/600/700 | Clean, readable at small sizes, neutral personality |
| Monospace | JetBrains Mono | 400/600 | Developer-friendly, ligatures off, tight line height for logs |
| Headings | Inter | 600/650 | Same family as UI for consistency |

### Scale

| Size / weight | Used for |
|---------------|----------|
| 28 / 650, -.02em | Page title (`.page-intro h1`) |
| 18 / 600 | Section heading |
| 14 / 400 | Card and form body copy |
| 13 / 600 | Card head title (`.card-head h2`) |
| 13 / 400 | Table row text, button labels |
| 11.5 / 400 | Metadata, field labels, card subtitles |
| 11 / 600, .05em caps | Table headers, KPI labels |
| 26 / 600 tabular | KPI values |
| mono 11.5—12 | Logs, hosts, ports, versions, timestamps |

## Color

### Dark Theme (default)

```
--bg-deep:       #070b14     (page background, deepest)
--bg:            #0c1123     (card surface)
--bg-elevated:   #111728     (hovered cards, inputs)
--bg-inset:      #161e33     (default button fill, inset surfaces)
--border:        #1e2742     (subtle borders)
--border-hover:  #2a3454     (hover borders)
--surface-header:#0a0f1e     (sidebar, sticky table headers)
--row-border:    #141c31     (table row separators — lighter than --border)
--text-primary:  #e2e8f0     (primary text)
--text-secondary:#8892b0     (secondary text)
--text-muted:    #5a6483     (muted text, placeholders)
```

The page background is flat `--bg-deep` — no gradient. The login page is the one exception
and carries a single radial wash, because it has no other content to carry the eye.

### Accent Palette

```
--accent:        #3b82f6     (primary actions, links — blue)
--accent-soft:   rgba(59,130,246,.12)
--accent-glow:   0 0 20px rgba(59,130,246,.25)
--accent-ink:    #06101f     (text ON the accent fill — see note below)

--success:       #22c55e     (healthy, active)
--success-soft:  rgba(34,197,94,.12)
--warning:       #eab308     (degraded, warning)
--warning-soft:  rgba(234,179,8,.12)
--danger:        #ef4444     (critical, failed)
--danger-soft:   rgba(239,68,68,.12)
--info:          #38bdf8     (in-progress work)
--info-soft:     rgba(56,189,248,.12)
--muted-soft:    rgba(90,100,131,.14)
```

Accent buttons use **dark ink** (`--accent-ink`) on the blue fill, not white: white on
`#3b82f6` measures 3.7:1 and fails AA for body text, `#06101f` on the same fill is 5.2:1.

Measured against `--bg`: text-primary 15.2:1, text-secondary 6.1:1, and every status colour
between 5.0:1 (danger) and 9.8:1 (warning). `--text-muted` is **3.2:1** and therefore only ever
carries metadata that is redundant — column labels, timestamps, placeholder text. Never make it
the sole carrier of information.


### Status → Color Mapping

| Status | Color | Usage |
|--------|-------|-------|
| healthy / active | success | Instance is running normally |
| warning | warning | Degraded but not failing |
| critical / failed / inactive | danger | Requires immediate attention |
| **wedged** | danger | systemd says `active`, the socket answers nothing — the state that produces the user-visible 5xx |
| **running / restarting / queued job** | info | Work in progress; nothing is wrong |
| unreachable / gone | text-muted | Server is not responding |
| unknown | text-secondary | Status not yet determined |

`info` is deliberately not a health state. A job that is running is neither healthy nor
degraded, and painting it amber trains operators to ignore amber.

## Spacing

Base unit 4px, scale `4 · 8 · 12 · 16 · 20 · 24 · 32 · 40`. Applied directly as pixel values,
not as custom properties — there are no `--space-*` variables in `style.css`.

- Card padding: 14px 20px (head), 20px (body)
- Table cells: 10px 14px
- Button padding: 8px 14px (default), 6px 10px (small)
- Sidebar: 208px wide, 18px 12px padding
- Topbar: 56px tall, 28px horizontal
- Grid gaps: 14px (cards, KPIs), 16px (page sections)

## Border Radius

```
--radius-sm: 6px
--radius-md: 10px
--radius-lg: 14px
```

## Shadows

```
--shadow-sm: 0 1px 2px rgba(0,0,0,.3)
--shadow-md: 0 1px 3px rgba(0,0,0,.35), 0 8px 24px -12px rgba(0,0,0,.5)
--shadow-lg: 0 1px 3px rgba(0,0,0,.4), 0 16px 48px -16px rgba(0,0,0,.6)
```

## Motion

- Duration: 150ms for micro-interactions, 200ms for transitions
- Easing: ease-out for exits, ease-out for entrances
- Pulse animation for live indicator (2s infinite)
- Toast: slide in from top (180ms ease-out)
- Dialog: fade in overlay + scale transition (200ms ease-out)

## Components

### Top Navigation

56px sticky bar, `rgba(12,17,35,.82)` with a 12px backdrop blur. Left: breadcrumb. Right: live
poller indicator and user chip. Branding lives in the sidebar, not here — it is not repeated.

### Side Navigation (desktop)

208px fixed sidebar on `--surface-header`, grouped by section label. Current route gets
`--accent-soft` fill plus a 2px inset accent rail on the left edge. Collapses to icons at
1100px and to an off-canvas drawer at 768px.

### Cards

Container for grouped content. Flat `--bg` surface, `--border`, `--radius-md`, `--shadow-md`.
Header carries the title, an optional subtitle, and either actions or a mono counter on the
right. **No card nested inside a card.**

### KPIs

Grid item showing a label, a value, and an optional detail line. Value is 26/600 tabular-nums,
coloured by status. Label is 11px uppercase muted.

### Tables

Full-width, sticky `--surface-header` header, rows separated by `--row-border` and hovering to
`--bg-elevated`. Numeric columns take `.num` (right-aligned, mono, tabular-nums) so digits line
up down the column. Status badges rather than coloured text.

### Buttons

| Variant | Usage |
|---------|-------|
| default | Secondary actions |
| accent/primary | Primary CTA |
| danger | Destructive actions |
| success | Positive actions (start) |
| warning | Cautionary actions (stop) |
| ghost | Minimal, for dense UIs |

Sizes: default (34px, 13px text), sm (30px, 12px text). No large.

Status variants (danger/success/warning) are soft-filled and **keep their colour on hover** —
the fill deepens from .12 to .2. A destructive button that turns solid red on hover reads as
"already pressed". Disabled buttons drop to `#0f1526` / `--text-muted` with `not-allowed`.

### Badges

Inline status indicators: 11/600 pill, `3px 9px`, soft background, matching text colour, and a
6px dot of the same colour. Used in tables, cards and detail views.

### Toasts

Fixed top-right stack. Each toast carries a 2px left rail in its status colour — that rail is
what registers peripherally; the icon just confirms it. Slides in over 180ms, auto-dismisses
after 4s (errors persist). Icon + message + close button.

### Dialogs

Modal overlay for confirmations and forms. Centred card, `--radius-lg`, `--border-hover`, 20px
padding, `--shadow-lg`. Title 15/600, body 13/1.55 secondary. Focus trap, close on Escape.
Confirmation copy names the exact target and the blast radius (see Design Rules).

### Forms

Cards with stacked label/input pairs. Inputs match elevated surface style. Help text in muted color below labels.

### Log Viewer

`--bg-deep` inset panel, `--border`, 8px radius, mono 11.5/1.75. Used for job details and
provisioning output. Line height is loose on purpose: operators read these under pressure.

## Design Rules

These four override anything else in this document.

1. **Status colour is load-bearing.** Never use success or danger decoratively. A green pill in
   this product means a live health check returned 200 — not "this looks nice here".
2. **Mono for machine values.** Hosts, ports, versions, keys, job ids, timestamps and log output
   are JetBrains Mono. Prose and labels are Inter. Mixing them is how a domain gets mistaken for
   a sentence.
3. **Destructive actions confirm.** Reboot, stop and remove open a dialog naming the exact
   target and the blast radius in instances. Stop also states that the instance stays down
   across reboots.
4. **Density over whitespace.** Operators scan 20+ rows at once: 10/14px table cells, 13px rows,
   no card nested inside a card.

## Component File Organization

All CSS is in `static/style.css`. No external CSS framework — custom properties power the design
system. Component classes follow BEM-like naming with utility overrides where needed.
`static/preview.html` renders every class against the real stylesheet; open it after a CSS change
instead of hunting components across the app.

## Empty States

Centred, utilitarian, no illustration: a `<strong>` headline stating what is missing, one line of
descriptive text saying what will happen once it exists, and a CTA link.

## Responsive Behavior

- Desktop (1100px+): Full experience, 208px labelled sidebar
- Tablet (768–1099px): Sidebar collapses to a 76px icon rail
- Mobile (<768px): Off-canvas sidebar behind the menu toggle, 2-up KPIs, tables scroll
  horizontally at a 700px minimum width, toasts span the full width
