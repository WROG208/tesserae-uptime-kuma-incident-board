# Changelog

All notable changes to this project are documented here.

## 1.1.4 - 2026-09-12

- Windows 95 summary badge, per-monitor glyphs, and taskbar state now follow the real health and cache state instead of always reading "ALL CLEAR", "✓", and "LIVE"
- Terminal footer reports the actual alarm count instead of a fixed "NO ACTIVE ALARMS", and the prompt shows the configured status-page slug
- Windows 3.11 Response History draws the fleet's recent heartbeat pings instead of a generated pattern; its footer reflects cached data
- Constellation, Orbital, Grafana, Grid, Minimal, Terminal, and DOS headline chrome switch to the alert colour when anything is down or an incident is open
- Grafana banner copy no longer says "no hidden credentials"

## 1.1.3 - 2026-09-12

- Fixed custom per-cell titles being replaced by a status-page title retained in the shared data cache
- Added regression coverage for custom titles and blank-title fallback across cached cells

## 1.1.2 - 2026-09-12

- Increased typography substantially across all nine layouts after the first enlargement remained too small during real-device review
- The rapid 1.1.0 through 1.1.2 patches reflect immediate readability and title testing on the 1872 x 1404 Seeed Studio reTerminal E1003 before the initial catalog submission was merged

## 1.1.1 - 2026-09-12

- Fixed the DOS header to use the configured widget title or Uptime Kuma status-page title

## 1.1.0 - 2026-09-12

- Added the DOS Network Manager display style
- Enlarged typography throughout all nine layouts for improved readability on e-paper displays
- Added server validation and test coverage for the DOS display selection

## 1.0.0 - 2026-09-12

- Initial public release by N4ASS
- Eight selectable display styles
- Public Uptime Kuma status-page and heartbeat collection
- Failure-first state and active-incident handling
- Responsive Tesserae `xs`, `sm`, `md`, and `lg` layouts
- Per-cell light, dark, density, history, and monitor-limit controls
- Configurable Orbital Constellation with automatic or explicit relationships
- One-minute cache with stale-data fallback and per-cell presentation isolation
- Server-side option validation and client-side HTML escaping
