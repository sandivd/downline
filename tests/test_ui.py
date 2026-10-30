"""Optional browser checks. Set DOWNLINE_CHROMIUM_PATH for a custom browser."""
from http.server import ThreadingHTTPServer
import importlib.util
import os
from pathlib import Path
import sys
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("downline_ui_app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


@pytest.fixture
def browser_page(tmp_path):
    e = app.Engine(tmp_path / "data", tmp_path / "tools-missing",
                   [sys.executable, str(ROOT / "tests/fake_engine.py")])
    e.settings.update(destination=str(tmp_path / "Downloads"), concurrency=1)
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    server.daemon_threads = True
    server.engine, server.token = e, "browser-test-token"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("DOWNLINE_CHROMIUM_PATH") or None,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"], headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 940}, color_scheme="light")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(f"http://127.0.0.1:{server.server_port}/#{server.token}")
        pw.expect(page.locator("#engine-status")).to_contain_text("Ready")
        yield page, e, errors
        context.close()
        browser.close()
    e.close()
    server.shutdown()
    server.server_close()


def test_theme_metadata_download_history_and_settings(browser_page):
    page, engine, errors = browser_page
    page.locator("#theme-toggle").click()
    pw.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    pw.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.locator("#video-url").fill("https://youtu.be/AAAAAAAAAAA")
    page.locator("#analyze").click()
    pw.expect(page.locator("#video-preview")).to_contain_text("A quiet afternoon <test>")
    assert page.locator("#video-preview test").count() == 0
    page.locator("#format").select_option("mp3")
    pw.expect(page.locator("#quality")).to_be_disabled()
    page.locator("#format").select_option("mp4")
    pw.expect(page.locator("#quality")).to_be_enabled()
    page.locator("#download").click()
    pw.expect(page.locator("#page-queue")).to_be_visible()
    page.locator('[data-page="history"]').click()
    pw.expect(page.locator("#history-jobs")).to_contain_text("Completed", timeout=10000)
    page.locator("#clear-history").click()
    page.locator("#confirm-yes").click()
    pw.expect(page.locator("#history-jobs")).to_contain_text("Nothing saved. Yet.")
    page.locator('[data-page="settings"]').click()
    page.locator("#setting-concurrency").select_option("3")
    page.locator('#settings-form button[type="submit"]').click()
    pw.expect(page.locator("#settings-message")).to_have_text("Changes saved.")
    assert engine.settings["concurrency"] == 3
    assert errors == []


def test_errors_batch_pause_and_cancel(browser_page):
    page, engine, errors = browser_page
    page.locator("#download").click()
    pw.expect(page.locator("#input-error")).to_contain_text("Paste a video link")
    page.locator("#video-url").fill("https://example.com/video")
    page.locator("#download").click()
    pw.expect(page.locator("#input-error")).to_contain_text("accepts YouTube")
    page.locator('[data-page="queue"]').click()
    page.locator("#pause-queue").click()
    pw.expect(page.locator("#queue-notice")).to_be_visible()
    page.locator('[data-page="new"]').click()
    page.locator("#video-url").fill("https://youtu.be/BBBBBBBBBBB\nhttps://youtu.be/AAAAAAAAAAA")
    page.locator("#download").click()
    pw.expect(page.locator("#queue-count")).to_have_text("2")
    assert all(j["status"] == "queued" for j in engine.jobs)
    page.locator('#queue-jobs [data-action="cancel"]').first.click()
    pw.expect(page.locator("#queue-count")).to_have_text("1")
    page.locator("#pause-queue").click()
    page.locator('[data-page="history"]').click()
    pw.expect(page.locator("#history-jobs")).to_contain_text("Completed", timeout=10000)
    assert len(errors) == 1 and "400 (Bad Request)" in errors[0]


def test_active_progress_and_cancellation(browser_page):
    page, engine, errors = browser_page
    page.locator("#video-url").fill("https://youtu.be/BBBBBBBBBBB")
    page.locator("#download").click()
    pw.expect(page.locator('#queue-jobs [role="progressbar"]')).to_be_visible()
    pw.expect(page.locator('#queue-jobs [role="progressbar"]')).to_have_attribute("aria-valuenow", "25", timeout=4000)
    width = page.locator("#queue-jobs .progress-fill").evaluate("el => el.style.width")
    assert width == "25%"
    page.locator('#queue-jobs [data-action="cancel"]').click()
    pw.expect(page.locator("#queue-count")).to_have_text("0")
    assert errors == []


def test_added_platforms_show_in_details_and_mixed_queue(browser_page):
    page, engine, errors = browser_page
    pw.expect(page.locator('.platform-list li')).to_have_count(6)
    page.locator('#video-url').fill('https://instagram.com/reel/AbCd123/')
    page.locator('#analyze').click()
    pw.expect(page.locator('#video-preview')).to_contain_text('Instagram')
    page.locator('[data-page="queue"]').click()
    page.locator('#pause-queue').click()
    pw.expect(page.locator('#queue-notice')).to_be_visible()
    page.locator('[data-page="new"]').click()
    page.locator('#video-url').fill('\n'.join([
        'https://instagram.com/reel/AbCd123/',
        'https://tiktok.com/@example/video/7123456789012345678',
        'https://twitter.com/example/status/1234567890',
        'https://twitch.tv/videos/1234567890',
    ]))
    page.locator('#download').click()
    pw.expect(page.locator('#queue-count')).to_have_text('4')
    for site in ('Instagram', 'TikTok', 'X (Twitter)', 'Twitch'):
        pw.expect(page.locator('#queue-jobs')).to_contain_text(site)
    assert all(j['status'] == 'queued' for j in engine.jobs)
    assert errors == []


@pytest.mark.parametrize("width,height,theme", [(1280, 940, "light"), (1280, 940, "dark"), (390, 844, "light"), (390, 844, "dark")])
def test_layout_has_no_horizontal_overflow(browser_page, width, height, theme):
    page, engine, errors = browser_page
    page.set_viewport_size({"width": width, "height": height})
    if theme == "dark":
        page.locator("#theme-toggle").click()
    for section in ("new", "queue", "history", "settings"):
        page.locator(f'[data-page="{section}"]').click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), section
        pw.expect(page.locator(f"#page-{section}")).to_be_visible()
    assert errors == []
