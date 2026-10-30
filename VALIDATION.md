# Validation

## Remove Reddit support — 30 October 2026

**94 checks passed; 1 skipped.** Removed Reddit from accepted URLs, logos, platform counts, documentation, and download/session settings. Undid the dedicated Reddit cookie-export and browser-details workflow. Existing saved Reddit settings are ignored and omitted the next time state is saved; user-selected export files are not modified or deleted. Existing history remains, and retry validates its URL against the current supported platforms so removed sources cannot restart.

Tests cover all six remaining platforms, formerly accepted Reddit link variants being rejected, old settings/history handling, queue behaviour, cookie export preservation, local API access, Brave Beta launch logic, and real local MP4/MKV/MP3 downloads/conversion. All eight browser checks passed. Both themes were rendered at desktop/narrow widths without overflow, and the six-logo layout was reviewed. The optional bootstrap-archive check was skipped; bootstrap/launcher files are unchanged. Live platform access remains unverified.

## Creator credit — 30 October 2026

Added a sidebar-footer credit linking Made by sandivd to https://github.com/sandivd in a new tab with noopener/noreferrer. The narrow sidebar displays the username. Verified the link destination and attributes, rendered both themes at desktop and narrow widths, and passed all four existing layout checks across all pages.

## Top-bar removal — 30 October 2026

Removed the shared top bar from every page and placed the Ready indicator at the upper-right of the content area. Removed the obsolete breadcrumb update from navigation. All eight browser checks passed across the app pages. Rendered light/dark desktop and narrow layouts without horizontal overflow and reviewed the dark-mode layouts.

## Label and status-dot update — 30 October 2026

Removed both Workspace labels and the breadcrumb separator, shortened the ready status to Ready, and brightened only the two status dots. Navigation spacing was adjusted after removing the sidebar label. All eight browser checks passed; the main screen was reviewed in dark mode, and both themes were rendered at desktop and narrow widths without horizontal overflow.

## Logo update — 30 October 2026

Replaced the seven platform names with locally embedded SVG logos. Logos keep accessible names and native hover titles. Reviewed the updated main screen in both themes at 1280px and 390px; no horizontal overflow was detected. All eight existing browser checks passed. Download/backend and launcher code were unchanged by this visual update, so the earlier 93-check result below remains the previous platform-release validation, not a rerun of the full suite for this update. Logo source details are in `LOGO-SOURCES.md`.

## Platform update — 30 October 2026

Validated this update with Python 3.12, yt-dlp 2026.10.26, FFmpeg, and headless Chromium 134.

- **93 automated checks passed; 1 skipped.** The optional bootstrap download check was skipped because its upstream archive and manifest were not supplied for this run. The setup script and its corrected checksum are byte-identical to the previous package.
- The 51 added platform checks cover accepted link forms, canonicalization, actual installed yt-dlp extractor matching for direct URLs, source labels in metadata and saved history, mixed-platform queue deduplication, rejection of profiles/live channels/spoofed hosts, first-video metadata for multi-video posts, and live/upcoming-stream filters.
- All eight browser checks passed, including a new mixed-platform queue test. The seven platform names wrap cleanly on narrow screens. Reviewed the main screen in light/dark themes at 1280px and 390px; the app screens have no horizontal overflow at the tested sizes.
- Existing lifecycle, API, cookie-copy, cancellation, and Brave Beta selection checks still pass. Real yt-dlp downloads from a local HTTP fixture still produce verified MP4, MKV, and MP3 outputs.
- Windows launcher and setup files remain unchanged. Windows execution, the native picker, and live transfers from any of the seven platforms were not verified in this run. Direct extractor matching and local fixtures do not prove current site access. Share-link resolution and restricted posts depend on the source site and the user's account session.

## Earlier release checks — 29 October 2026

Validated in the build environment on 29 October 2026 with Python 3.12, yt-dlp 2026.10.26, FFmpeg, and headless Chromium 153.

- **42 automated checks passed**: 26 backend and real-media checks, 7 browser checks, 8 browser-launch regressions, and 1 real-download bootstrap check.
- Real yt-dlp downloaded a local MP4 fixture through HTTP. FFmpeg successfully produced MP4, MKV, and MP3 outputs; ffprobe confirmed the expected audio/video streams. The MP4 fixture remained byte-identical.
- Checked supported URL normalization and rejection, queue deduplication, failure/retry, cancellation of active processes, queue pause/resume, cookie export preservation and temporary-copy cleanup, history clearing without file deletion, and interrupted-session restoration.
- Checked local API token/origin enforcement and that source files cannot be requested through the UI server.
- Browser checks covered metadata display, HTML escaping, theme persistence, audio controls, download completion, history clearing, settings, batch input, validation errors, pause/cancel, and live progress rendering.
- Visually reviewed the main screen in light and dark modes and the narrow-screen main/settings layouts. Checked all screens for horizontal overflow at desktop and narrow widths.

The Windows bootstrap and native folder picker were reviewed as source; this environment cannot run Windows executables. Live YouTube and Pornhub transfers were not verified here. Those depend on current site behaviour, account access, region, and network connectivity. The tests do not claim otherwise.

## Windows setup repair

The initial launcher paired the `embeddable-amd64.zip` URL with the checksum for the different `embed-amd64.zip` archive. Corrected the pin for the exact download URL and confirmed it by downloading the real archive and comparing it with Python's official `windows-3.13.17.json` manifest. SHA-256: `0ba1ee4bfcbdc3a559d27e2e9ce76d04a7839947a23f46375872c755c0d463b8`.

The dedicated bootstrap regression check passed against the downloaded archive and manifest. The archive's CRC checks passed, and the expected Python executables, standard library, and path configuration were present. Setup now reuses an already downloaded archive when its checksum is valid and removes a failed download automatically.

Also downloaded the actual Windows yt-dlp executable, FFmpeg ZIP, and Deno ZIP from the launcher URLs. The yt-dlp checksum matched its upstream checksum list. Both other ZIPs passed CRC checks and contained their required executables. These checks validate the downloads; Windows execution remains unverified.

To run the optional runtime pin check, set `DOWNLINE_BOOTSTRAP_CHECK_DIR` to a folder containing the upstream `python.zip` and `python-manifest.json`, then run `python -m pytest tests/test_bootstrap.py -q`. This adds one check when its real downloads are supplied.

To reproduce the full suite in a development environment with dependencies installed:

```sh
python -m pytest tests -q
```

The browser checks require Playwright and its Chromium browser. `DOWNLINE_CHROMIUM_PATH` can select an existing compatible executable. Tests use temporary folders; no sample download history, account cookies, or runtime binaries are included in the distributed ZIP.

## Brave Beta launcher update

Windows launches use an explicitly saved executable or a detected Brave Beta installation in Program Files, Program Files (x86), or Local AppData. **Choose Brave Beta.cmd** forces a native file chooser and remembers the user's exact executable path, including custom installation locations. If Beta cannot be found or started, the Windows launcher reports an error instead of falling back to another browser. The selected file is user-designated; the launcher does not independently attest its release channel.

Eight regression checks cover saving and reusing a custom path, changing a saved selection, missing Beta while ordinary Brave is installed, cancelled selection, launch failure, moved or invalid executables, service reuse without swallowing browser errors, and cleanup after a failed first launch. The launch record contains the requested executable path without its private session URL. These checks exercise selection and service logic; the native Windows chooser and Brave Beta executable cannot be run in this environment.
