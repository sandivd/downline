# Push Downline to GitHub

This folder combines the current Windows app source and the static website. Nothing has been pushed or published yet.

1. Create a new **public** repository named **Downline** under **sandivd**. Leave the automatic README, licence and gitignore options unchecked because these files are already included.
2. Extract this ZIP. Open the inner `Downline` folder. Its root should contain `app.py`, `README.md`, `ui`, `tests`, `dist`, and `.github`.
3. Push the contents of this inner folder, not the ZIP or another outer `Downline` folder.

From a terminal in this folder, for a new empty GitHub repository:

```sh
git init
git add .
git commit -m "Initial Downline release"
git branch -M main
git remote add origin https://github.com/sandivd/Downline.git
git push -u origin main
```

If a repository or Git history already exists, preserve it; don't blindly rerun this new-repository sequence or force-push. Copy these files into the existing checkout and review the changes instead.

The `.github` folder and `.gitignore` file must be included. The gitignore has been adjusted so `dist/downloads/Downline-Windows.zip` is committed while root downloads and runtime files remain ignored. You can confirm the website download is tracked with:

```sh
git ls-files dist/downloads/Downline-Windows.zip
```

After pushing, select **Settings → Pages → Source → GitHub Actions**. Run or rerun **Deploy website to GitHub Pages** from the Actions tab if needed. The workflow publishes the `dist` directory. Open the site URL GitHub returns when deployment succeeds.

Later, make a GitHub Release and attach `dist/downloads/Downline-Windows.zip` as its downloadable asset. The website's download button already works from the tracked copy, so creating a Release isn't required for the first website deployment. Instructions for switching to a real release URL are in `website-docs/README.md`.

The current Windows build requires Brave Beta and downloads its runtime tools on first launch. These requirements are stated on the website. No local runtime, cookies, browser profile, personal settings or downloaded videos are included in this folder.
