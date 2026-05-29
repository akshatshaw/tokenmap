# Changelog

All notable changes to **tokenmap** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-05-29

### Added
- `--since` / `--until` date-range filters (`YYYY-MM-DD`, inclusive). `--year`
  is kept as sugar for a full calendar year.
- `--model <name>` filter to isolate a single model (case-insensitive substring
  match) across both the heatmap and the cost breakdown.
- CSV export via `--export csv` — one row per day with token counts and an
  estimated cost.
- `--json --out <file>` writes the raw stats JSON to a file (previously stdout
  only).
- `--no-claude` and `--no-cost` flags.

### Changed
- **Defaults.** Claude Code data is now included by default (other installed
  tools are still auto-detected on top), the estimated cost breakdown is shown
  by default, the default theme is now `dark-green`, and file export is now
  opt-in — runs are terminal-only unless you pass `--export`/`--out`/`--copy`.
- `--export` now accepts `csv` in addition to `png` and `svg`.
- Environment variables renamed: `TOKENMAP_CONCURRENCY` (was
  `BRAGGRID_CONCURRENCY`) and `TOKENMAP_MAX_RECORD_BYTES` (was
  `BRAGGRID_MAX_RECORD_BYTES`). The old names still work for one release.

### Fixed
- Added `claude-opus-4-8` to the pricing table ($5 in / $25 out / $6.25 cache
  write / $0.50 cache read per MTok). It previously fell through to the legacy
  `claude-opus-4` rate ($15/$75) and overstated cost ~3×.
- Version string is now consistent across the package (`__version__`,
  `--version`, and packaging metadata were out of sync).
- Completed a truncated sentence in the README privacy section.

### Deprecated
- `BRAGGRID_CONCURRENCY` and `BRAGGRID_MAX_RECORD_BYTES` environment variables.
  Use the `TOKENMAP_*` equivalents; the old names will be removed in a future
  release.

## [0.1.2] - 2026-05-10

### Fixed
- Cost calculation was being clobbered by Claude's lifetime `modelUsage`
  totals. Cost now derives from the dated `statsCache` block, so year/date
  filters are respected.

## [0.1.1] - 2026-04-18

### Changed
- Switched PNG rendering to PyMuPDF, fixing image-rendering issues.
- Published to PyPI as `tokenmap`.

## [0.1.0] - 2026-04-18

### Added
- Initial release: GitHub-style contribution heatmap for AI coding tool usage,
  with adapters for Claude Code, Codex, OpenCode, and Cursor; terminal, SVG, and
  PNG renderers; and Claude/OpenAI cost estimation.

[0.1.3]: https://github.com/akshatshaw/tokenmap/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/akshatshaw/tokenmap/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/akshatshaw/tokenmap/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/akshatshaw/tokenmap/releases/tag/v0.1.0
