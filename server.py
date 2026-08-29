#!/usr/bin/env python3
"""
ToolEV Local Server & API
Serves static web files, supports video streaming with Range requests,
and handles video processing requests via background tasks.
"""
import os
import sys
import json
import uuid
import time
import shutil
import mimetypes
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

# Ensure UTF-8 IO
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
OUTPUT_DIR = BASE_DIR / "output"

sys.path.insert(0, str(SCRIPTS_DIR))
from pipeline import process_video

TASKS = {}
TASKS_LOCK = threading.Lock()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ToolEVRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.path = "/all-video.html"
            return super().do_GET()

        if path == "/api/videos":
            return self.handle_get_videos()

        if path == "/api/status":
            query = parse_qs(parsed.query)
            task_id = query.get("task_id", [""])[0]
            with TASKS_LOCK:
                task = TASKS.get(task_id)
            if not task:
                return self.send_json({"error": "Task not found"}, 404)
            return self.send_json(task)

        # Handle range requests for media files
        if path.startswith("/output/") or path.endswith((".mp4", ".m4a", ".mp3", ".webm")):
            return self.handle_media_file(path)

        return super().do_GET()

    def handle_get_videos(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        clips = []

        for item in OUTPUT_DIR.iterdir():
            if not item.is_dir():
                continue

            slug = item.name
            ielts_file = item / "ielts_listening.json"
            mp4_file = item / "video.mp4"
            thumb_file = item / "thumb.jpg"
            if not thumb_file.exists():
                thumb_candidates = list(item.glob("*.jpg")) + list(item.glob("*.png")) + list(item.glob("*.webp"))
                thumb_file = thumb_candidates[0] if thumb_candidates else None

            parts_dir = item / "parts"
            has_parts = parts_dir.is_dir() and any(parts_dir.glob("*_transcript.json"))

            title = slug.replace("_", " ")
            youtube_id = None
            created_at = int(item.stat().st_mtime * 1000)

            has_ielts = ielts_file.exists()
            if has_ielts:
                try:
                    with open(ielts_file, "r", encoding="utf-8") as fp:
                        meta = json.load(fp)
                        if meta.get("title"):
                            title = meta["title"]
                        if meta.get("youtube_id"):
                            youtube_id = meta["youtube_id"]
                        if meta.get("created_at"):
                            try:
                                from datetime import datetime
                                dt = datetime.fromisoformat(meta["created_at"].replace("Z", "+00:00"))
                                created_at = int(dt.timestamp() * 1000)
                            except Exception:
                                pass
                except Exception:
                    pass

            clip = {
                "slug": slug,
                "title": title,
                "hasMp4": mp4_file.exists(),
                "mp4Url": f"/output/{slug}/video.mp4" if mp4_file.exists() else None,
                "hasIelts": has_ielts,
                "ieltsUrl": f"/output/{slug}/ielts_listening.json" if has_ielts else None,
                "hasTranscript": has_parts,
                "partsUrl": f"/output/{slug}/parts/part_000_transcript.json" if has_parts else None,
                "thumbUrl": f"/output/{slug}/{thumb_file.name}" if thumb_file and thumb_file.exists() else (
                    f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg" if youtube_id else None
                ),
                "youtubeId": youtube_id,
                "createdAt": created_at,
                "updatedAt": created_at,
            }
            clips.append(clip)

        clips.sort(key=lambda c: c["createdAt"], reverse=True)
        return self.send_json(clips)

    def handle_media_file(self, req_path):
        rel_path = req_path.lstrip("/")
        file_path = BASE_DIR / rel_path

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File not found")
            return

        file_size = file_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

        range_header = self.headers.get("Range")
        if range_header:
            # Parse Range: bytes=START-END
            try:
                range_spec = range_header.strip().split("=")[1]
                start_str, end_str = range_spec.split("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                if end >= file_size:
                    end = file_size - 1
                length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(file_path, "rb") as f:
                    f.seek(start)
                    bytes_to_send = length
                    while bytes_to_send > 0:
                        chunk_size = min(bytes_to_send, 64 * 1024)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        self.wfile.write(data)
                        bytes_to_send -= len(data)
                return
            except Exception as e:
                pass

        # Normal full file response
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(file_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/process":
            return self.handle_post_process()

        if path == "/api/delete":
            return self.handle_post_delete()

        self.send_error(404, "Endpoint not found")

    def handle_post_process(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
        except Exception as e:
            return self.send_json({"error": f"Invalid JSON payload: {e}"}, 400)

        url = data.get("url", "").strip()
        lang = data.get("language", "en").strip()
        if not url:
            return self.send_json({"error": "Missing 'url' parameter"}, 400)

        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "url": url,
            "status": "running",
            "percent": 0,
            "step": "Bắt đầu khởi tạo",
            "logs": [],
            "result": None,
            "error": None,
            "created_at": time.time()
        }

        with TASKS_LOCK:
            TASKS[task_id] = task_data

        def worker():
            def cb(pct, step_name, msg=""):
                with TASKS_LOCK:
                    t = TASKS.get(task_id)
                    if t:
                        t["percent"] = pct
                        t["step"] = step_name
                        if msg:
                            t["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")

            try:
                res = process_video(url, language=lang, progress_cb=cb)
                with TASKS_LOCK:
                    t = TASKS.get(task_id)
                    if t:
                        t["status"] = "completed"
                        t["percent"] = 100
                        t["step"] = "Hoàn tất"
                        t["result"] = res
            except Exception as e:
                with TASKS_LOCK:
                    t = TASKS.get(task_id)
                    if t:
                        t["status"] = "error"
                        t["error"] = str(e)
                        t["logs"].append(f"❌ Lỗi: {str(e)}")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        return self.send_json({"task_id": task_id, "status": "running"})

    def handle_post_delete(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            slug = data.get("slug", "").strip()
            if not slug:
                return self.send_json({"error": "Missing slug"}, 400)

            target = OUTPUT_DIR / slug
            if target.exists() and target.is_dir():
                shutil.rmtree(target)
                return self.send_json({"success": True})
            else:
                return self.send_json({"error": "Slug directory not found"}, 404)
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)


def run_server(port=8000):
    for p in range(port, port + 10):
        try:
            server_address = ("", p)
            httpd = ThreadedHTTPServer(server_address, ToolEVRequestHandler)
            print(f"🚀 ToolEV server running at: http://localhost:{p}/")
            print(f"👉 Mở trình duyệt: http://localhost:{p}/all-video.html")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nStopping server...")
                httpd.server_close()
            return
        except OSError as e:
            if p == port + 9:
                print(f"[LỖI] Không thể mở cổng mạng: {e}")
                raise


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
