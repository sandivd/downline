"""Downline: a local, dependency-free UI server for the yt-dlp executable."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, urlunsplit, urlencode
from urllib.request import Request, urlopen
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parent
ACTIVE = {"starting", "downloading", "processing", "cancelling"}
TERMINAL = {"completed", "failed", "cancelled"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SITE_HOSTS = {
    "YouTube": {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"},
    "Pornhub": {"pornhub.com", "www.pornhub.com", "m.pornhub.com", "pornhub.org", "www.pornhub.org"},
    "Instagram": {"instagram.com", "www.instagram.com", "m.instagram.com"},
    "TikTok": {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"},
    "X (Twitter)": {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"},
    "Twitch": {"twitch.tv", "www.twitch.tv", "m.twitch.tv", "go.twitch.tv", "clips.twitch.tv"},
}


def site_name(url):
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return next((name for name, hosts in SITE_HOSTS.items() if host in hosts), "Video")


def validate_url(raw):
    if not isinstance(raw, str) or len(raw) > 2048 or re.search(r"[\x00-\x20\x7f]", raw):
        raise ValueError("Paste a valid video link without spaces.")
    try:
        p = urlsplit(raw if "://" in raw else "https://" + raw)
        if p.scheme not in {"http", "https"} or p.username or p.password or p.port not in {None, 80, 443}:
            raise ValueError()
        host = (p.hostname or "").lower().rstrip(".")
    except ValueError:
        raise ValueError("That video link is not valid.") from None
    q = parse_qs(p.query)
    if host in SITE_HOSTS["YouTube"]:
        video = (p.path.strip("/").split("/")[0] if host.endswith("youtu.be") else
                 q.get("v", [""])[0] if p.path == "/watch" else
                 p.path.strip("/").split("/")[1] if p.path.startswith(("/shorts/", "/live/", "/embed/")) else "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ValueError("Use a link to one YouTube video or Short, rather than a channel or playlist.")
        return "https://www.youtube.com/watch?" + urlencode({"v": video})
    if host in SITE_HOSTS["Pornhub"]:
        key = q.get("viewkey", [""])[0]
        if p.path.rstrip("/") != "/view_video.php" or not re.fullmatch(r"[A-Za-z0-9_-]{5,100}", key):
            raise ValueError("Use a Pornhub video link containing view_video.php?viewkey=…")
        domain = "www.pornhub.org" if host.endswith(".org") else "www.pornhub.com"
        return urlunsplit(("https", domain, "/view_video.php", urlencode({"viewkey": key}), ""))
    if host in SITE_HOSTS["Instagram"]:
        match = re.fullmatch(r"/(?:(?!share/)[A-Za-z0-9_.]+/)?(p|tv|reel|reels)/([A-Za-z0-9_-]+)/?", p.path)
        if match:
            kind = "reel" if match[1] == "reels" else match[1]
            return f"https://www.instagram.com/{kind}/{match[2]}/"
        if re.fullmatch(r"/share/(?:reel|p|tv)/[A-Za-z0-9_-]+/?", p.path):
            return urlunsplit(("https", "www.instagram.com", p.path.rstrip("/") + "/", "", ""))
        raise ValueError("Use an Instagram Reel or video post link, rather than a profile.")
    if host in SITE_HOSTS["TikTok"]:
        match = re.fullmatch(r"/(?:@([A-Za-z0-9_.-]+)/video|share/video|embed(?:/v2)?)/(\d+)/?", p.path)
        if match:
            user = "@" + match[1] if match[1] else "share"
            return f"https://www.tiktok.com/{user}/video/{match[2]}"
        if host in {"vm.tiktok.com", "vt.tiktok.com"} and re.fullmatch(r"/[A-Za-z0-9_-]+/?", p.path):
            return urlunsplit(("https", host, p.path.rstrip("/") + "/", "", ""))
        if re.fullmatch(r"/t/[A-Za-z0-9_-]+/?", p.path):
            return urlunsplit(("https", "www.tiktok.com", p.path.rstrip("/") + "/", "", ""))
        raise ValueError("Use a TikTok video or shared video link, rather than a profile or live channel.")
    if host in SITE_HOSTS["X (Twitter)"]:
        match = re.fullmatch(r"/(?:[A-Za-z0-9_]+/status|i/web/status|statuses)/(\d+)(/video/[1-9]\d*)?/?", p.path)
        if match:
            # Keep explicit media indices so /video/2 does not become /video/1.
            return "https://x.com/i/web/status/" + match[1] + (match[2] or "")
        raise ValueError("Use an X / Twitter post link containing /status/ and a video.")
    if host in SITE_HOSTS["Twitch"]:
        match = re.fullmatch(r"/videos/(\d+)/?", p.path)
        if host != "clips.twitch.tv" and match:
            return "https://www.twitch.tv/videos/" + match[1]
        match = re.fullmatch(r"/[A-Za-z0-9_]+/clip/([A-Za-z0-9_-]+)/?", p.path)
        if host != "clips.twitch.tv" and match:
            return "https://clips.twitch.tv/" + match[1]
        if host == "clips.twitch.tv" and re.fullmatch(r"/[A-Za-z0-9_-]+/?", p.path) and p.path.strip("/") != "embed":
            return "https://clips.twitch.tv/" + p.path.strip("/")
        if host == "clips.twitch.tv" and p.path == "/embed" and re.fullmatch(r"[A-Za-z0-9_-]+", q.get("clip", [""])[0]):
            return "https://clips.twitch.tv/" + q["clip"][0]
        raise ValueError("Use a Twitch clip or past broadcast link (/videos/…). Live channels are not supported.")
    raise ValueError("Downline accepts YouTube, Pornhub, Instagram, TikTok, X (Twitter), and Twitch video links.")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def default_data_dir():
    return Path(os.environ.get("DOWNLINE_DATA_DIR") or
                Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Downline")


def stop_process(proc):
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


class Engine:
    def __init__(self, data_dir=None, tools_dir=None, command=None):
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.tools_dir = Path(tools_dir or ROOT / "runtime/tools")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.closing = threading.Event()
        self.processes = {}
        self.aux_processes = set()
        self.updating = False
        self.command_override = command
        self.paused = False
        self.settings = {"destination": str(Path.home() / "Downloads/Downline"), "concurrency": 2,
                         "remember_history": True, "cookies": ""}
        self.jobs = []
        try:
            saved = json.loads((self.data_dir / "state.json").read_text(encoding="utf-8"))
            self.settings.update({k: v for k, v in saved.get("settings", {}).items() if k in self.settings})
            self.settings["concurrency"] = max(1, min(3, int(self.settings["concurrency"])))
            self.jobs = saved.get("jobs", []) if isinstance(saved.get("jobs"), list) else []
            for j in self.jobs:
                if j["status"] in ACTIVE or j["status"] == "queued":
                    j.update(status="cancelled", error="Interrupted when the app closed. Retry to continue.")
        except (OSError, ValueError, KeyError, TypeError):
            self.jobs = []
        self.scheduler = threading.Thread(target=self._schedule, daemon=True)
        self.scheduler.start()

    def command(self):
        if self.command_override:
            return list(self.command_override)
        binary = self.tools_dir / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")
        if binary.exists():
            return [str(binary)]
        system = shutil.which("yt-dlp")
        if system:
            return [system]
        return None

    def dependencies(self):
        def exists(name):
            return (self.tools_dir / (name + (".exe" if os.name == "nt" else ""))).is_file() or bool(shutil.which(name))
        return {"engine": bool(self.command()), "ffmpeg": exists("ffmpeg"), "javascript": exists("deno") or exists("node")}

    def base_command(self):
        cmd = self.command()
        if not cmd:
            raise ValueError("The download engine is missing. Close Downline and run Start Downline.cmd again.")
        cmd += ["--ignore-config", "--no-plugin-dirs", "--no-playlist", "--playlist-items", "1", "--no-colors", "--encoding", "utf-8",
                "--socket-timeout", "20", "--retries", "3", "--extractor-retries", "2"]
        if self.tools_dir.exists():
            cmd += ["--ffmpeg-location", str(self.tools_dir)]
        for runtime in ("deno", "node"):
            local = self.tools_dir / (runtime + (".exe" if os.name == "nt" else ""))
            if local.exists():
                cmd += ["--js-runtimes", runtime + ":" + str(local)]
                break
            if shutil.which(runtime):
                cmd += ["--js-runtimes", runtime]
                break
        if self.settings.get("cookies"):
            path = Path(self.settings["cookies"])
            if not path.is_file():
                raise ValueError("The selected cookies file is missing. Update it in Settings.")
            # yt-dlp saves its cookie jar on exit. Always use a private temporary
            # copy so the user's original export is never changed.
            cmd += ["--cookies", str(path)]
        return cmd

    def _spawn(self, cmd):
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", bufsize=1,
                                creationflags=NO_WINDOW, start_new_session=os.name != "nt")

    def _cookie_copy(self, cmd, folder):
        if "--cookies" in cmd:
            idx = cmd.index("--cookies") + 1
            target = folder / "cookies.txt"
            shutil.copyfile(cmd[idx], target)
            cmd[idx] = str(target)
        return cmd

    def analyze(self, raw):
        import tempfile
        url = validate_url(raw.strip())
        with tempfile.TemporaryDirectory(prefix="downline-info-") as tmp:
            with self.lock:
                if self.updating or self.closing.is_set():
                    raise ValueError("The engine is busy. Try again in a moment.")
                if len(self.aux_processes) >= 3:
                    raise ValueError("A few video lookups are already running. Try again in a moment.")
                cmd = self._cookie_copy(self.base_command(), Path(tmp)) + ["--dump-single-json", "--skip-download", "--", url]
                proc = self._spawn(cmd)
                self.aux_processes.add(proc)
            try:
                output, _ = proc.communicate(timeout=65)
            except subprocess.TimeoutExpired:
                stop_process(proc)
                proc.communicate()
                raise ValueError("The site took too long to respond. Try again.") from None
            finally:
                with self.lock:
                    self.aux_processes.discard(proc)
            if proc.returncode:
                raise ValueError(self.error_text(output))
            try:
                info = next(json.loads(line) for line in reversed(output.splitlines()) if line.startswith("{"))
            except (StopIteration, ValueError):
                raise ValueError("The site did not return video details.") from None
        # A single social post can contain several videos. Each queue entry
        # saves its first video, so show details for that same video.
        while info.get("entries") is not None:
            parent = info
            info = next((entry for entry in info["entries"] if isinstance(entry, dict)), None)
            if info is None:
                raise ValueError("This post did not contain a downloadable video.")
            info = {**{k: parent[k] for k in ("title", "uploader", "channel") if parent.get(k)}, **info}
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise ValueError("This is a live stream. Try again after the broadcast finishes.")
        return {"url": url, "title": str(info.get("title") or "Untitled video"),
                "uploader": str(info.get("uploader") or info.get("channel") or ""),
                "duration": info.get("duration"), "site": site_name(url),
                "qualities": sorted({int(f["height"]) for f in info.get("formats", [])
                                     if isinstance(f.get("height"), (int, float)) and f["height"] > 0}, reverse=True)}

    @staticmethod
    def error_text(output):
        if "does not pass filter" in output and ("is_live" in output or "is_upcoming" in output):
            return "This is a live or upcoming stream. Try again after the broadcast finishes."
        lines = [re.sub(r"\x1b\[[0-9;]*m", "", x) for x in output.splitlines() if "ERROR:" in x]
        message = (lines[-1] if lines else "The download engine could not complete this request.").replace("ERROR: ", "")
        # URLs can include ephemeral tokens; avoid displaying them in the UI.
        return re.sub(r"https?://\S+", "[video link]", message)[-900:]

    def save(self):
        with self.lock:
            atomic_json(self.data_dir / "state.json", {"settings": self.settings,
                        "jobs": self.jobs[-500:] if self.settings["remember_history"] else []})

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({"jobs": self.jobs, "settings": self.settings, "paused": self.paused,
                                  "updating": self.updating, "dependencies": self.dependencies()})

    def enqueue(self, payload):
        raws = payload.get("urls", [])
        if not isinstance(raws, list) or not 1 <= len(raws) <= 50:
            raise ValueError("Add between 1 and 50 video links at a time.")
        urls = list(dict.fromkeys(validate_url(u.strip()) for u in raws if isinstance(u, str)))
        if not urls:
            raise ValueError("Paste at least one video link.")
        fmt, quality = payload.get("format", "mp4"), str(payload.get("quality", "best"))
        if fmt not in {"mp4", "mkv", "mp3"} or quality not in {"best", "2160", "1440", "1080", "720", "480", "360"}:
            raise ValueError("Choose a supported format and quality.")
        with self.lock:
            if self.updating:
                raise ValueError("Wait for the engine update to finish.")
            dest = Path(self.settings["destination"]).expanduser().resolve()
            dest.mkdir(parents=True, exist_ok=True)
            added = []
            for url in urls:
                duplicate = any(j["url"] == url and j["format"] == fmt and j["quality"] == quality
                                and j["status"] not in TERMINAL for j in self.jobs)
                if duplicate:
                    continue
                job = {"id": uuid.uuid4().hex, "url": url, "title": "Getting video details…", "site":
                       site_name(url), "format": fmt, "quality": quality,
                       "status": "queued", "progress": 0, "speed": None, "eta": None, "bytes": 0,
                       "destination": str(dest), "path": "", "error": "", "created": time.time(), "phase": ""}
                self.jobs.append(job)
                added.append(job["id"])
            self.save()
        self.wake.set()
        return {"added": len(added)}

    def build_download_command(self, job):
        # Some hosts omit stream heights. Keep those formats eligible instead
        # of rejecting an otherwise downloadable video outright.
        limit = "" if job["quality"] == "best" else "[height<=?" + job["quality"] + "]"
        work = Path(job["destination"]) / ".downline-partials" / job["id"]
        work.mkdir(parents=True, exist_ok=True)
        cmd = self._cookie_copy(self.base_command(), work)
        cmd += ["--match-filters", "!is_live & live_status !=? is_upcoming", "--newline", "--progress", "--progress-delta", "0.3", "--continue", "--no-overwrites",
                "--windows-filenames", "--trim-filenames", "160", "--no-mtime",
                "--paths", "home:" + job["destination"], "--paths", "temp:" + str(work),
                "--output", "%(title).120B [%(id)s] " + job["id"][:8] + ".%(ext)s",
                "--print", "before_dl:DL_META:%(.{title,duration})j",
                "--print", "after_move:DL_FILE:%(filepath)j", "--no-simulate",
                "--progress-template", "download:DL_PROGRESS:%(progress)j"]
        if job["format"] == "mp3":
            cmd += ["--format", "bestaudio/best", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]
        elif job["format"] == "mp4":
            # Prefer H.264/AAC for wide Windows compatibility. The fallback is
            # remuxed, never silently transcoded; MKV retains best source codecs.
            selector = (f"bestvideo{limit}[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
                        f"best{limit}[ext=mp4]/bestvideo{limit}[ext=mp4]+bestaudio[ext=m4a]/best{limit}")
            cmd += ["--format", selector, "--merge-output-format", "mp4", "--remux-video", "mp4"]
        else:
            cmd += ["--format", f"bestvideo{limit}+bestaudio/best{limit}",
                    "--merge-output-format", "mkv", "--remux-video", "mkv"]
        return cmd + ["--", job["url"]]

    def _schedule(self):
        while not self.closing.is_set():
            with self.lock:
                if not self.paused and not self.updating:
                    slots = self.settings["concurrency"] - sum(j["status"] in ACTIVE for j in self.jobs)
                    for job in [j for j in self.jobs if j["status"] == "queued" and j["id"] not in self.processes][:max(0, slots)]:
                        job["status"] = "starting"
                        threading.Thread(target=self._run, args=(job,), daemon=True).start()
            self.wake.wait(.5)
            self.wake.clear()

    def _run(self, job):
        proc, logs = None, []
        try:
            with self.lock:
                if job["status"] == "cancelling" or self.closing.is_set():
                    job["status"] = "cancelled"
                    return
                proc = self._spawn(self.build_download_command(job))
                self.processes[job["id"]] = proc
                job["status"] = "downloading"
            for raw in proc.stdout:
                line = raw.strip()
                with self.lock:
                    if line.startswith("DL_META:"):
                        try:
                            job["title"] = json.loads(line[8:]).get("title") or "Untitled video"
                        except (ValueError, AttributeError):
                            pass
                    elif line.startswith("DL_PROGRESS:") and job["status"] != "cancelling":
                        try:
                            p = json.loads(line[12:])
                            total = p.get("total_bytes") or p.get("total_bytes_estimate") or 0
                            done = p.get("downloaded_bytes") or 0
                            pct = 100 * done / total if total else None
                            job.update(status="processing" if p.get("status") == "finished" else "downloading",
                                       progress=min(100, max(0, pct)) if pct is not None else None,
                                       speed=p.get("speed"), eta=p.get("eta"), bytes=done,
                                       phase="Merging / converting" if p.get("status") == "finished" else "Downloading stream")
                        except (ValueError, TypeError):
                            pass
                    elif line.startswith("DL_FILE:"):
                        try:
                            job["path"] = json.loads(line[8:])
                        except ValueError:
                            pass
                    else:
                        logs.append(line)
                        logs = logs[-40:]
            code = proc.wait()
            with self.lock:
                if job["status"] == "cancelling" or self.closing.is_set():
                    job.update(status="cancelled", speed=None, eta=None, error="Cancelled. Retry to continue partial downloads.")
                elif code == 0 and job["path"] and Path(job["path"]).is_file():
                    job.update(status="completed", progress=100, speed=None, eta=None, finished=time.time(),
                               bytes=Path(job["path"]).stat().st_size)
                else:
                    job.update(status="failed", error=self.error_text("\n".join(logs)), speed=None, eta=None)
        except Exception as exc:
            with self.lock:
                if job["status"] == "cancelling" or self.closing.is_set():
                    job.update(status="cancelled", error="Cancelled.")
                else:
                    job.update(status="failed", error=str(exc)[:900])
        finally:
            stop_process(proc)
            with self.lock:
                self.processes.pop(job["id"], None)
                cookie_copy = Path(job["destination"]) / ".downline-partials" / job["id"] / "cookies.txt"
                try:
                    cookie_copy.unlink(missing_ok=True)
                except OSError:
                    pass
                self.save()
            self.wake.set()

    def action(self, action, job_id=None):
        with self.lock:
            if action == "pause":
                self.paused = not self.paused
            elif action == "clear":
                self.jobs = [j for j in self.jobs if j["status"] not in TERMINAL]
            else:
                job = next((j for j in self.jobs if j["id"] == job_id), None)
                if not job:
                    raise ValueError("This download is no longer in your queue.")
                if action == "cancel":
                    if job["status"] == "queued":
                        job["status"] = "cancelled"
                    elif job["status"] in ACTIVE:
                        job["status"] = "cancelling"
                        proc = self.processes.get(job_id)
                        threading.Thread(target=stop_process, args=(proc,), daemon=True).start()
                elif action == "retry" and job["status"] in {"failed", "cancelled"}:
                    validate_url(job["url"])
                    job.update(status="queued", error="", progress=0, speed=None, eta=None)
                elif action == "remove" and job["status"] in TERMINAL:
                    self.jobs.remove(job)
                else:
                    raise ValueError("That action is unavailable for this download.")
            self.save()
        self.wake.set()
        return {"ok": True}

    def update_settings(self, data):
        dest = str(data.get("destination", self.settings["destination"])).strip()
        path = Path(dest).expanduser()
        if not dest or not path.is_absolute():
            raise ValueError("Choose a full folder path, such as C:\\Users\\Sandiv\\Downloads\\Downline.")
        try:
            count = int(data.get("concurrency", self.settings["concurrency"]))
        except (TypeError, ValueError):
            raise ValueError("Choose 1, 2, or 3 simultaneous downloads.") from None
        if count not in {1, 2, 3}:
            raise ValueError("Choose 1, 2, or 3 simultaneous downloads.")
        cookies = str(data.get("cookies", self.settings["cookies"])).strip()
        if cookies and not Path(cookies).is_file():
            raise ValueError("Choose an existing Netscape cookies.txt file, or leave it empty.")
        path.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.settings.update(destination=str(path.resolve()), concurrency=count, cookies=cookies,
                                 remember_history=bool(data.get("remember_history", self.settings["remember_history"])))
            self.save()
        self.wake.set()
        return {"ok": True}

    def update_engine(self):
        with self.lock:
            if self.updating or self.aux_processes or any(j["status"] in ACTIVE or j["status"] == "queued" for j in self.jobs):
                raise ValueError("Finish or cancel your queue before updating the engine.")
            self.updating = True
        proc = None
        try:
            cmd = self.command()
            if not cmd or len(cmd) != 1 or not Path(cmd[0]).is_relative_to(self.tools_dir):
                raise ValueError("For a source installation, update yt-dlp with your package manager.")
            proc = self._spawn(cmd + ["--ignore-config", "--update"])
            with self.lock:
                self.aux_processes.add(proc)
            try:
                output, _ = proc.communicate(timeout=150)
            except subprocess.TimeoutExpired:
                stop_process(proc)
                proc.communicate()
                raise ValueError("Update timed out. Try again later.") from None
            if proc.returncode:
                raise ValueError(self.error_text(output))
            return {"ok": True, "message": "Download engine is up to date."}
        finally:
            stop_process(proc)
            with self.lock:
                self.aux_processes.discard(proc)
                self.updating = False

    def close(self):
        self.closing.set()
        with self.lock:
            for job in self.jobs:
                if job["status"] in ACTIVE:
                    job["status"] = "cancelling"
            processes = list(self.processes.values()) + list(self.aux_processes)
        for proc in processes:
            stop_process(proc)
        self.save()


def native_picker(kind):
    if os.name != "nt":
        raise ValueError("Type a folder or file path in Settings on this operating system.")
    dialog = ("$d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Save videos to'; "
              "$d.ShowNewFolderButton=$true" if kind == "folder" else
              "$d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='Cookies text file (*.txt)|*.txt|All files (*.*)|*.*'")
    field = "SelectedPath" if kind == "folder" else "FileName"
    script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
              "$f=New-Object System.Windows.Forms.Form; $f.TopMost=$true; " + dialog +
              "; if($d.ShowDialog($f) -eq 'OK'){[Console]::Write($d." + field + ")}; $f.Dispose()")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                         text=True, encoding="utf-8-sig", creationflags=NO_WINDOW, timeout=300)
    return {"path": out.stdout.strip()}


def open_local(path, reveal=False):
    p = Path(path).resolve()
    if not p.exists():
        raise ValueError("This file or folder was moved or deleted.")
    if os.name == "nt":
        if reveal:
            subprocess.Popen(["explorer.exe", "/select,", str(p)], creationflags=NO_WINDOW)
        else:
            os.startfile(str(p))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", *( ["-R"] if reveal else []), str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p.parent if reveal and p.is_file() else p)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def reply(self, code, body, mime="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self, auth=False):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            self.reply(403, {"error": "Invalid local host."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + expected:
            self.reply(403, {"error": "This request must come from Downline."})
            return False
        if auth and not secrets.compare_digest(self.headers.get("X-Downline-Token", ""), self.server.token):
            self.reply(401, {"error": "Session expired. Reopen Downline using its launcher."})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.allowed(auth=path.startswith("/api/")):
            return
        if path == "/api/state":
            self.reply(200, self.server.engine.snapshot())
        elif path == "/api/ping":
            self.reply(200, {"app": "Downline", "version": "1.0.0"})
        else:
            assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                      "/style.css": ("style.css", "text/css"), "/icon.svg": ("icon.svg", "image/svg+xml")}
            if path not in assets:
                self.reply(404, {"error": "Not found."})
                return
            name, mime = assets[path]
            self.reply(200, (ROOT / "ui" / name).read_bytes(), mime)

    def do_POST(self):
        if not self.allowed(auth=True):
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 131072:
                self.reply(413, {"error": "Request is too large or empty."})
                return
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected a request object.")
            engine, path = self.server.engine, urlsplit(self.path).path
            if path == "/api/analyze":
                result = engine.analyze(str(payload.get("url", "")))
            elif path == "/api/download":
                result = engine.enqueue(payload)
            elif path == "/api/action":
                result = engine.action(payload.get("action"), payload.get("id"))
            elif path == "/api/settings":
                result = engine.update_settings(payload)
            elif path == "/api/pick":
                result = native_picker(payload.get("kind", "folder"))
            elif path == "/api/open":
                if payload.get("id"):
                    with engine.lock:
                        job = next((j for j in engine.jobs if j["id"] == payload["id"] and j["status"] == "completed"), None)
                        if not job:
                            raise ValueError("Download this video before opening it.")
                        file_path = job["path"]
                    result = open_local(file_path, bool(payload.get("reveal")))
                else:
                    folder = Path(engine.settings["destination"])
                    folder.mkdir(parents=True, exist_ok=True)
                    result = open_local(folder)
            elif path == "/api/update":
                result = engine.update_engine()
            elif path == "/api/quit":
                result = {"ok": True}
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.reply(404, {"error": "Not found."})
                return
            self.reply(200, result)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            self.reply(400, {"error": str(exc)[:1000]})
        except Exception:
            self.reply(500, {"error": "Something went wrong. Close and reopen Downline."})


def launch_window(url):
    """Open the local interface using the system's default web browser."""
    if os.name == "nt":
        try:
            os.startfile(url)
        except OSError as exc:
            raise RuntimeError("Could not open your default browser. Set a default web browser in Windows Settings and try again.") from exc
        return
    if not webbrowser.open(url):
        raise RuntimeError("Could not open your default browser. Set a default web browser and try again.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    instance = default_data_dir() / "instance.json"
    if not args.no_browser:
        existing_url = None
        try:
            existing = json.loads(instance.read_text())
            url = "http://127.0.0.1:" + str(int(existing["port"]))
            req = Request(url + "/api/ping", headers={"X-Downline-Token": existing["token"]})
            with urlopen(req, timeout=2) as response:
                if json.load(response).get("app") == "Downline":
                    existing_url = url + "/#" + existing["token"]
        except (OSError, ValueError, KeyError):
            pass
        if existing_url is not None:
            launch_window(existing_url)
            return
    engine = Engine()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.engine, server.token = engine, secrets.token_urlsafe(32)
    atomic_json(instance, {"port": server.server_port, "token": server.token})
    url = f"http://127.0.0.1:{server.server_port}/#{server.token}"
    if sys.stdout:
        print("Downline is ready at " + url, flush=True)
    try:
        if not args.no_browser:
            launch_window(url)
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
        server.server_close()
        try:
            if json.loads(instance.read_text()).get("token") == server.token:
                instance.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
