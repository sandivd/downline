"""Platform routing checks; fixture downloads do not verify live site access."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("downline_platforms", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

CASES = [
    ("https://m.instagram.com/reel/AbCd_12-/?igsh=tracking", "https://www.instagram.com/reel/AbCd_12-/", "Instagram", "Instagram"),
    ("instagram.com/p/AbCd123/", "https://www.instagram.com/p/AbCd123/", "Instagram", "Instagram"),
    ("https://www.instagram.com/someone/reels/AbCd123/?utm_source=copy", "https://www.instagram.com/reel/AbCd123/", "Instagram", "Instagram"),
    ("https://www.instagram.com/tv/AbCd123/", "https://www.instagram.com/tv/AbCd123/", "Instagram", "Instagram"),
    ("https://www.instagram.com/share/reel/AbCd123/", "https://www.instagram.com/share/reel/AbCd123/", "Instagram", None),
    ("https://m.tiktok.com/@example/video/7123456789012345678?is_from_webapp=1", "https://www.tiktok.com/@example/video/7123456789012345678", "TikTok", "TikTok"),
    ("https://www.tiktok.com/embed/v2/7123456789012345678", "https://www.tiktok.com/share/video/7123456789012345678", "TikTok", "TikTok"),
    ("https://vm.tiktok.com/ZM1234567/?share=1", "https://vm.tiktok.com/ZM1234567/", "TikTok", "TikTokVM"),
    ("https://vt.tiktok.com/ZM1234567/", "https://vt.tiktok.com/ZM1234567/", "TikTok", "TikTokVM"),
    ("tiktok.com/t/ZM1234567/?share=1", "https://www.tiktok.com/t/ZM1234567/", "TikTok", "TikTokVM"),
    ("https://mobile.twitter.com/example/status/1234567890?s=20", "https://x.com/i/web/status/1234567890", "X (Twitter)", "Twitter"),
    ("https://x.com/example/status/1234567890/video/2?ref_src=share", "https://x.com/i/web/status/1234567890/video/2", "X (Twitter)", "Twitter"),
    ("https://x.com/i/web/status/1234567890", "https://x.com/i/web/status/1234567890", "X (Twitter)", "Twitter"),
    ("https://m.twitch.tv/videos/1234567890?t=1h2m", "https://www.twitch.tv/videos/1234567890", "Twitch", "TwitchVod"),
    ("https://www.twitch.tv/example/clip/FriendlyClip-AbC123?filter=clips", "https://clips.twitch.tv/FriendlyClip-AbC123", "Twitch", "TwitchClips"),
    ("https://clips.twitch.tv/FriendlyClip-AbC123?tt_medium=clips_api", "https://clips.twitch.tv/FriendlyClip-AbC123", "Twitch", "TwitchClips"),
    ("https://clips.twitch.tv/embed?clip=FriendlyClip-AbC123&parent=example.com", "https://clips.twitch.tv/FriendlyClip-AbC123", "Twitch", "TwitchClips"),
]


@pytest.mark.parametrize("raw,canonical,site,extractor", CASES)
def test_new_platform_urls_are_normalized_and_route_to_real_extractors(raw, canonical, site, extractor):
    assert app.validate_url(raw) == canonical
    assert app.validate_url(canonical) == canonical
    assert app.site_name(canonical) == site
    if extractor:
        yt = pytest.importorskip("yt_dlp.extractor")
        cls = yt.get_info_extractor(extractor)
        assert cls.suitable(canonical), f"{canonical} did not reach {extractor}"


@pytest.mark.parametrize("raw", [
    "https://instagram.com/example", "https://instagram.com/reels/audio/123/",
    "https://tiktok.com/@example", "https://tiktok.com/@example/live", "https://tiktok.com/t/",
    "https://reddit.com/r/videos/", "https://v.redd.it/abc/DASH_720.mp4",
    "https://twitter.com/example", "https://x.com/example/status/nope", "https://x.com/example/status/123/video/0",
    "https://twitch.tv/example", "https://twitch.tv/directory", "https://twitch.tv/example/videos",
    "https://clips.twitch.tv/embed?parent=example.com", "https://clips.twitch.tv/",
    "https://instagram.com.evil.example/reel/AbCd123/", "https://tiktok.com@127.0.0.1/@example/video/123",
    "https://www.reddit.com:444/comments/abc123/", "https://evil.x.com/example/status/123",
    "https://x.com/example/status/123\n--exec=bad", "https://twitch.tv/videos/123%0a--exec=bad",
])
def test_profiles_livestreams_and_spoofed_links_are_rejected(raw):
    with pytest.raises(ValueError):
        app.validate_url(raw)


@pytest.fixture
def engine(tmp_path):
    e = app.Engine(tmp_path / "data", tmp_path / "tools", [sys.executable, str(ROOT / "tests/fake_engine.py")])
    e.paused = True
    e.settings["destination"] = str(tmp_path / "downloads")
    yield e
    e.close()


def test_mixed_queue_preserves_sources_and_deduplicates_aliases(engine):
    urls = ["https://youtu.be/AAAAAAAAAAA", "https://pornhub.com/view_video.php?viewkey=ph12345"]
    urls += [CASES[index][0] for index in (0, 5, 10, 13)]
    urls += ["https://x.com/example/status/1234567890", "https://tiktok.com/@example/video/7123456789012345678"]
    assert engine.enqueue({"urls": urls}) == {"added": 6}
    assert [j["site"] for j in engine.jobs] == ["YouTube", "Pornhub", "Instagram", "TikTok", "X (Twitter)", "Twitch"]
    restored = json.loads((engine.data_dir / "state.json").read_text())
    assert [j["site"] for j in restored["jobs"]] == [j["site"] for j in engine.jobs]


@pytest.mark.parametrize("index", [0, 5, 10, 13])
def test_analyze_uses_correct_source_label(engine, index):
    raw, canonical, site, _ = CASES[index]
    info = engine.analyze(raw)
    assert info["site"] == site
    assert info["url"] == canonical
    assert info["title"] == "A quiet afternoon <test>"


def test_multi_video_post_details_match_first_downloaded_video(engine, monkeypatch):
    proc = Mock(returncode=0)
    proc.communicate.return_value = (json.dumps({"title": "Post title", "entries": [
        {"title": "First video", "duration": 4, "formats": [{"height": 720}]},
    ]}), "")
    monkeypatch.setattr(engine, "_spawn", Mock(return_value=proc))
    info = engine.analyze(CASES[1][0])
    assert info["title"] == "First video" and info["qualities"] == [720]
    command = engine._spawn.call_args.args[0]
    assert command[command.index("--playlist-items") + 1] == "1"


def test_live_broadcasts_are_rejected_even_if_details_step_is_skipped(engine, monkeypatch):
    proc = Mock(returncode=0)
    proc.communicate.return_value = ('{"is_live": true}', "")
    monkeypatch.setattr(engine, "_spawn", Mock(return_value=proc))
    with pytest.raises(ValueError, match="after the broadcast"):
        engine.analyze(CASES[13][0])
    engine.enqueue({"urls": [CASES[13][0]]})
    command = engine.build_download_command(engine.jobs[0])
    assert command[command.index("--match-filters") + 1] == "!is_live & live_status !=? is_upcoming"
    pytest.importorskip("yt_dlp")
    from yt_dlp.utils import match_filter_func
    filter_fn = match_filter_func("!is_live & live_status !=? is_upcoming")
    assert filter_fn({"is_live": True}) is not None
    assert filter_fn({"live_status": "is_upcoming"}) is not None
    assert filter_fn({"is_live": False, "live_status": "was_live"}) is None
    assert filter_fn({}) is None
    assert "after the broadcast" in app.Engine.error_text("[download] Stream does not pass filter (!is_live & live_status !=? is_upcoming), skipping ..")


@pytest.mark.parametrize("url", ['https://old.reddit.com/r/videos/comments/AbC123/some_title/?share_id=abc', 'https://reddit.com/user/example/comments/abc123/title/', 'https://redd.it/AbC123', 'https://www.reddit.com/r/videos/s/Share123?utm_source=share', 'https://v.redd.it/abc123xyz/', 'https://www.reddit.com/comments/abc123/'])
def test_removed_reddit_links_are_no_longer_accepted(url):
    with pytest.raises(ValueError, match="Downline accepts"):
        app.validate_url(url)


def test_old_reddit_settings_are_ignored_and_history_cannot_retry_removed_platform(tmp_path):
    export = tmp_path / 'reddit-export.txt'
    export.write_text('# Netscape HTTP Cookie File\n')
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'state.json').write_text(json.dumps({
        'settings': {'reddit_cookies': str(export), 'reddit_user_agent': 'fixture-agent'},
        'jobs': [{'id': 'old-reddit-job', 'site': 'Reddit', 'url': 'https://www.reddit.com/comments/abc123/', 'status': 'failed'}],
    }))
    engine = app.Engine(data_dir, tmp_path / 'tools')
    try:
        assert 'reddit_cookies' not in engine.settings
        assert 'reddit_user_agent' not in engine.settings
        with pytest.raises(ValueError, match='Downline accepts'):
            engine.action('retry', 'old-reddit-job')
        assert engine.jobs[0]['status'] == 'failed'
    finally:
        engine.close()
    assert export.exists()
    persisted = json.loads((data_dir / 'state.json').read_text())
    assert 'reddit_cookies' not in persisted['settings']
    assert len(persisted['jobs']) == 1
