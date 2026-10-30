# Validation

## Default browser startup — 30 October 2026

**89 automated checks passed; 1 optional check skipped.**

The Windows launcher opens the local app URL using the system HTTP browser association. Other operating systems use Python's default-browser handler. No executable picker, per-browser launch arguments, browser-specific detection or saved browser preference is used. Existing saved browser configuration files are ignored and left untouched.

The launcher regression checks cover system dispatch, ignored legacy configuration, actionable launch errors, opening an existing service, cleanup after a failed first launch, and headless startup. Native Windows browser associations and PowerShell cannot run in this Linux environment; Windows dispatch is covered with mocks.

Backend checks cover supported platform URLs, API access, queue behavior, cookie export preservation and real local MP4/MKV/MP3 media processing. The optional upstream bootstrap archive check requires external cached archives and is skipped when they are unavailable. The app interface is unchanged, so the existing optional browser UI suite was not rerun for this launcher and website-copy change.

The downloadable Windows app and both website packages are rebuilt together. ZIP integrity, matching app source across packages, and removal of retired browser integration content are checked before delivery.
