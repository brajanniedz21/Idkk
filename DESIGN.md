# Design

Terminal-native dark market UI. The reference is a dealing desk at night: amber phosphor heritage, near-black surfaces, numbers as the primary graphic element. Not a Bloomberg pastiche; a modern instrument built with that discipline.

## Color

Strategy: Restrained. Neutrals carry the frame; amber is the brand and selection color; green/red are reserved exclusively for market direction and are never decorative.

```css
:root {
  --bg:        oklch(0.13 0 0);        /* app background */
  --panel:     oklch(0.17 0 0);        /* panels, table headers */
  --panel-2:   oklch(0.21 0 0);        /* hover rows, inputs */
  --line:      oklch(0.28 0 0);        /* hairline borders */
  --ink:       oklch(0.92 0 0);        /* primary text */
  --muted:     oklch(0.66 0 0);        /* secondary text ≥4.5:1 */
  --faint:     oklch(0.50 0 0);        /* timestamps, footnotes (large/mono only) */
  --amber:     oklch(0.84 0.14 88);    /* brand, selection, index, focus */
  --up:        oklch(0.76 0.17 155);   /* gains — validated #3fce7c */
  --down:      oklch(0.62 0.19 22);    /* losses — validated #e5484d */
  --halt:      oklch(0.75 0.15 65);    /* warnings, halts */
}
```

Direction is never color-alone: every green/red value carries a sign (+/−) and often an arrow (▲/▼).

## Typography

Two families, contrast axis mono vs sans:

- Data (prices, tickers, tables, timestamps, chart labels): `ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace`, 11 to 13px, `font-variant-numeric: tabular-nums`.
- Prose (pitches, comments, reports, empty states): `system-ui, -apple-system, "Segoe UI", sans-serif`, 13 to 14px.
- Scale ratio 1.2, fixed rem. The only large type is the selected instrument's last price.
- Uppercase only for panel labels of four words or fewer (TOP GAINERS, FLOOR FEED).

## Voice

Wire-service dry. No exclamation marks, no emoji, no congratulations. Prices report; the reader feels. Buttons are verb + object ("Place order", "Issue guidance", "Log session").

## Components

- Panels: 1px `--line` full border, flat, 2px radius max. No shadows, no glass, no gradients.
- Tables: 24px rows, hairline row separators, right-aligned numerics, mono.
- Price flash: 300ms background pulse (green/red at 15% alpha) on change.
- Ticker tape: CSS linear scroll, pauses on hover, static under prefers-reduced-motion.
- Charts: canvas candlesticks (thin bodies, 1px wicks), volume band below on shared x-axis, recessive gridlines, right-edge last-price tag, crosshair with OHLC readout in the chart header, not a floating tooltip.
- Focus: 1px amber outline, 2px offset, everywhere.

## Motion

150 to 250ms, ease-out only. Motion conveys state: price flash, feed prints sliding in 150ms, bell banner at open/close. Nothing animates on page load. All of it collapses to instant under prefers-reduced-motion.
