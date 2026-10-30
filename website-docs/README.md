# Downline website

A static landing page for Downline, using the three supplied screenshots. No build step, package installation, backend, accounts or API keys. The Windows app is included as a ZIP download; the site itself does not download videos.

## Preview

Open `dist/index.html`. Theme switching, screenshot tabs, FAQ and the app download all work without a server. Some browsers restrict saving theme preferences for local files.

## Publish to GitHub Pages

This package has not been pushed to GitHub or published. Create or choose your website repository under **sandivd**. Upload the **contents of this folder**, preserving `dist` and `.github/workflows/pages.yml`; don't upload the outer `Downline-Website` folder as another nesting level.

In the repository's **Settings → Pages**, choose **GitHub Actions** as the source. The included workflow publishes `dist` when changes are pushed to `main`. You can also run it manually in the Actions tab. Repository names and domains are not hard-coded, so project Pages URLs work too.

If using the browser upload interface, make sure the `.github/workflows/pages.yml` file is included: Windows can hide dot-prefixed folders. Alternatively publish the contents of `dist` from a Pages branch. See GitHub's current Pages documentation for the exact UI: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages

## App downloads and GitHub Releases

The download link currently points to `dist/downloads/Downline-Windows.zip`, which is the unchanged current Windows app package. It works immediately in a local preview and after deployment. This is a source-and-launcher ZIP, not an installer or standalone EXE. The app downloads its runtime tools on first launch and currently requires Brave Beta.

Once you create a GitHub Release, upload `Downline-Windows.zip` as its asset, then replace the download button's relative `href` in `dist/index.html` with that real release asset URL. For a cross-origin release URL, remove the `download` attribute and let GitHub's asset response handle the download. Delete the now-unneeded `dist/downloads/Downline-Windows.zip` after updating the link. No repository or release URL has been invented in this website.

For a combined app-and-website repository, keep the app at the root and add this package's `dist` and workflow without overwriting the app README, LICENSE or other existing files. This package leaves the Windows app unchanged.

## Files

- `dist/index.html` — content and accessible HTML
- `dist/styles.css` — responsive dark/light themes
- `dist/app.js` — theme persistence and keyboard-accessible screenshot tabs
- `dist/assets/` — the supplied screenshots, app icon and bundled platform logos
- `dist/downloads/Downline-Windows.zip` — current Windows app
- `.github/workflows/pages.yml` — optional GitHub Pages deployment
- `.openai/hosting.json` — local preview configuration; not needed by GitHub Pages

All assets load locally. No analytics, third-party scripts, external fonts or tracking are added. Logo attribution is in `LOGO-SOURCES.md`. App dependencies, licensing and setup details remain in the Windows ZIP.
