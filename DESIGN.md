# OpenAlgo Fleet Manager — Design System

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

- Body: 13px (tables), 14px (cards, forms)
- Small: 11.5px (metadata, labels)
- Monospace: 11.5px—12px (logs, URLs, keys)

## Color

### Dark Theme (default)

```
--bg-deep:       #070b14     (page background, deepest)
--bg:            #0c1123     (card surface)
--bg-elevated:   #111728     (hovered cards, inputs)
--bg-inset:      #161e33     (inset surfaces, table rows)
--border:        #1e2742     (subtle borders)
--border-hover:  #2a3454     (hover borders)
--text-primary:  #e2e8f0     (primary text)
--text-secondary:#8892b0     (secondary text)
--text-muted:    #5a6483     (muted text, placeholders)
```

### Accent Palette

```
--accent:        #3b82f6     (primary actions, links — blue)
--accent-soft:   rgba(59,130,246,.12)
--accent-glow:   0 0 20px rgba(59,130,246,.25)

--success:       #22c55e     (healthy, active)
--success-soft:  rgba(34,197,94,.12)
--warning:       #eab308     (degraded, warning)
--warning-soft:  rgba(234,179,8,.12)
--danger:        #ef4444     (critical, failed)
--danger-soft:   rgba(239,68,68,.12)
--info:          #38bdf8     (informational)
--info-soft:     rgba(56,189,248,.12)
```

### Status → Color Mapping

| Status | Color | Usage |
|--------|-------|-------|
| healthy / active | success | Instance is running normally |
| warning | warning | Degraded but not failing |
| critical / failed / inactive | danger | Requires immediate attention |
| unreachable / gone | text-muted | Server is not responding |
| unknown | text-secondary | Status not yet determined |

## Spacing

Base unit: 4px

```
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px
--space-5: 20px
--space-6: 24px
--space-8: 32px
--space-10: 40px
```

- Card padding: 16px 20px (head), 16px 20px (body)
- Table cells: 10px 14px
- Button padding: 8px 14px (default), 6px 10px (small)
- KPI grid gap: 14px

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

Sticky bar with brand, nav links, live status indicator, and user menu. Backdrop blur with semi-transparent background.

### Side Navigation (desktop)

Collapsible sidebar with grouped navigation. Current section highlighted with accent bar.

### Cards

Container for grouped content. Elevated surface with border, radius, shadow. Optional header with title + actions.

### KPIs

Grid item showing a label and value. Value uses tabular-nums for alignment. Color-coded by status.

### Tables

Full-width with sticky header, subtle row hover, mono for data values. Status badges for scannable health indicators.

### Buttons

| Variant | Usage |
|---------|-------|
| default | Secondary actions |
| accent/primary | Primary CTA |
| danger | Destructive actions |
| success | Positive actions (start) |
| warning | Cautionary actions (stop) |
| ghost | Minimal, for dense UIs |

Sizes: default, sm (small only — no large needed)

### Badges

Inline status indicators. Pill-shaped with soft background and matching text color. Used in tables and detail views.

### Toasts

Fixed position top-right notification stack. Slides in, auto-dismisses after 4s (errors persist). Icon + message + close button.

### Dialogs

Modal overlay for confirmations and forms. Centered card with backdrop. Focus trap, close on Escape.

### Forms

Cards with stacked label/input pairs. Inputs match elevated surface style. Help text in muted color below labels.

### Log Viewer

Monospace, dark inset panel with scrolling log output. Used for job details and provisioning output.

## Component File Organization

All CSS is in `static/style.css`. No external CSS framework — custom properties power the design system. Component classes follow BEM-like naming with utility overrides where needed.

## Empty States

When no data exists, show centered message with descriptive text and a CTA link. No illustration needed — keep it utilitarian.

## Responsive Behavior

- Desktop (1024px+): Full experience with sidebar
- Tablet (768-1023px): Collapsed sidebar, reduced padding
- Mobile (<768px): Single column, stacked KPIs, scrollable tables
