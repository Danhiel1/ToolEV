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
import traceback
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

# Safe IO for pythonw / windowless GUI execution
class SafeOutput:
    def __init__(self, target=None):
        self.target = target

    def write(self, s):
        if self.target is not None:
            try:
                self.target.write(s)
            except Exception:
                pass

    def flush(self):
        if self.target is not None:
            try:
                self.target.flush()
            except Exception:
                pass

    def reconfigure(self, **kwargs):
        pass

if sys.stdout is None:
    sys.stdout = SafeOutput()
else:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = SafeOutput()
else:
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
OUTPUT_DIR = BASE_DIR / "output"
BIN_DIR = BASE_DIR / "bin"
VENV_DIR = SCRIPTS_DIR / ".venv"
VENV_SITE = VENV_DIR / "Lib" / "site-packages"

# Tự động nạp ffmpeg/ffprobe từ bin/ vào PATH nếu có
if BIN_DIR.is_dir():
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

# Tự động nạp Scripts của .venv vào PATH nếu có
if (VENV_DIR / "Scripts").is_dir():
    os.environ["PATH"] = str(VENV_DIR / "Scripts") + os.pathsep + os.environ.get("PATH", "")

# Tự động nạp thư viện AI (faster-whisper, ctranslate2) từ .venv nếu chạy ngoài venv
if VENV_SITE.is_dir() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SCRIPTS_DIR))
from logger import get_logger, get_recent_logs, get_raw_logs, clear_logs, get_log_file_path, setup_logging
setup_logging()
logger = get_logger("server")

from pipeline import process_video
from vocab_service import lookup_word, lookup_words_batch, VocabStore

TASKS = {}
TASKS_LOCK = threading.Lock()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ToolEVRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def address_string(self):
        # Tránh DNS lookup getfqdn gây trễ 2 giây trên Windows
        return self.client_address[0]

    def log_message(self, format, *args):
        try:
            logger.info(f"{self.client_address[0]} - {format % args}")
        except Exception:
            pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            try:
                logger.debug(f"send_json socket error: {e}")
            except Exception:
                pass

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/" or path == "/index.html":
                self.path = "/all-video.html"
                return super().do_GET()

            if path == "/manifest.json":
                manifest = {
                    "name": "ToolEV",
                    "short_name": "ToolEV",
                    "start_url": "/all-video.html",
                    "display": "standalone",
                    "background_color": "#0d1117",
                    "theme_color": "#161b22"
                }
                return self.send_json(manifest)

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

            if path == "/api/logs":
                query = parse_qs(parsed.query)
                max_lines = 200
                if "lines" in query and query["lines"][0].isdigit():
                    max_lines = int(query["lines"][0])
                lines = get_recent_logs(max_lines=max_lines)
                log_file = get_log_file_path()
                size = log_file.stat().st_size if log_file.exists() else 0
                return self.send_json({
                    "lines": lines,
                    "total_lines": len(lines),
                    "file": str(log_file),
                    "size_bytes": size
                })

            if path == "/api/logs/raw":
                content = get_raw_logs()
                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/translate":
                query = parse_qs(parsed.query)
                word = query.get("q", [""])[0] or query.get("word", [""])[0]
                ctx = query.get("context", [""])[0]
                res = lookup_word(word, context=ctx)
                return self.send_json(res)

            if path == "/api/vocab":
                query = parse_qs(parsed.query)
                status_filter = query.get("status", ["all"])[0]
                slug_filter = query.get("slug", ["all"])[0]
                items = VocabStore.get_all(filter_status=status_filter, filter_slug=slug_filter)
                return self.send_json({"vocab": items, "items": items, "total": len(items)})

            if path == "/api/vocab/export":
                query = parse_qs(parsed.query)
                fmt = query.get("format", ["csv"])[0]
                if fmt == "csv":
                    content = VocabStore.export_csv()
                    body = content.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="toolev_vocab.csv"')
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                else:
                    items = VocabStore.get_all()
                    return self.send_json(items)

            if path == "/api/shutdown":
                self.send_json({"success": True, "message": "Server is shutting down..."})
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return

            # Handle range requests for media files
            if path.startswith("/output/") or path.endswith((".mp4", ".m4a", ".mp3", ".webm")):
                return self.handle_media_file(path)

            return super().do_GET()
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Error handling GET {self.path}: {e}\n{tb}")
            return self.send_json({"error": f"Internal Server Error: {str(e)}", "traceback": tb}, 500)

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
            transcript_files = sorted(parts_dir.glob("*_transcript.json")) if parts_dir.is_dir() else []
            has_parts = len(transcript_files) > 0
            transcript_urls = [f"/output/{slug}/parts/{p.name}" for p in transcript_files]

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
                "transcriptUrls": transcript_urls if has_parts else None,
                "partsUrl": transcript_urls[0] if transcript_urls else None,
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
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/process":
                return self.handle_post_process()

            if path in ("/api/delete", "/api/videos/delete"):
                return self.handle_post_delete()

            if path == "/api/translate":
                return self.handle_post_translate()

            if path == "/api/translate/batch":
                return self.handle_post_translate_batch()

            if path == "/api/vocab/save":
                return self.handle_post_vocab_save()

            if path == "/api/vocab/delete":
                return self.handle_post_vocab_delete()

            if path == "/api/vocab/status":
                return self.handle_post_vocab_status()

            if path == "/api/logs/clear":
                ok = clear_logs()
                return self.send_json({"success": ok, "message": "Log cleared successfully"})

            if path == "/api/shutdown":
                self.send_json({"success": True, "message": "Server is shutting down..."})
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return

            self.send_error(404, "Endpoint not found")
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Error handling POST {self.path}: {e}\n{tb}")
            return self.send_json({"error": f"Internal Server Error: {str(e)}", "traceback": tb}, 500)


    def handle_post_delete(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            slug = data.get("slug", "").strip()
            if not slug or ".." in slug or "/" in slug or "\\" in slug:
                return self.send_json({"error": "Invalid slug parameter"}, 400)

            deleted_items = []
            # 1. Thư mục chuẩn mới: output/<slug>/
            target_dir = OUTPUT_DIR / slug
            if target_dir.exists() and target_dir.is_dir():
                shutil.rmtree(target_dir, ignore_errors=True)
                deleted_items.append(str(target_dir))

            # 2. Cấu trúc legacy đơn lẻ: output/<slug>.mp4, output/<slug>_parts, etc.
            legacy_mp4 = OUTPUT_DIR / f"{slug}.mp4"
            if legacy_mp4.exists():
                try:
                    legacy_mp4.unlink()
                    deleted_items.append(str(legacy_mp4))
                except Exception:
                    pass

            legacy_parts = OUTPUT_DIR / f"{slug}_parts"
            if legacy_parts.exists() and legacy_parts.is_dir():
                shutil.rmtree(legacy_parts, ignore_errors=True)
                deleted_items.append(str(legacy_parts))

            legacy_thumb = OUTPUT_DIR / f"{slug}_thumb.jpg"
            if legacy_thumb.exists():
                try:
                    legacy_thumb.unlink()
                    deleted_items.append(str(legacy_thumb))
                except Exception:
                    pass

            legacy_tr = OUTPUT_DIR / f"{slug}_transcript.json"
            if legacy_tr.exists():
                try:
                    legacy_tr.unlink()
                    deleted_items.append(str(legacy_tr))
                except Exception:
                    pass

            return self.send_json({
                "success": True,
                "slug": slug,
                "message": f"Đã xoá bài học '{slug}' thành công",
                "deleted": deleted_items
            })
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)


    def handle_post_translate(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            word = data.get("q", "") or data.get("word", "")
            ctx = data.get("context", "")
            res = lookup_word(word, context=ctx)
            return self.send_json(res)
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)

    def handle_post_translate_batch(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            words = data.get("words", [])
            if not isinstance(words, list):
                return self.send_json({"error": "words must be an array"}, 400)
            res = lookup_words_batch(words)
            return self.send_json({"results": res, "total": len(res)})
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)

    def handle_post_vocab_save(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            item = VocabStore.save_item(data)
            return self.send_json({"success": True, "item": item})
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)

    def handle_post_vocab_delete(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            target = data.get("id") or data.get("word")
            if not target:
                return self.send_json({"error": "Missing id or word"}, 400)
            ok = VocabStore.delete_item(target)
            return self.send_json({"success": ok})
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)

    def handle_post_vocab_status(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            target = data.get("id") or data.get("word")
            st = data.get("status", "need_review")
            if not target:
                return self.send_json({"error": "Missing id or word"}, 400)
            ok = VocabStore.update_status(target, st)
            return self.send_json({"success": ok})
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)


    def handle_post_process(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
        except Exception as e:
            return self.send_json({"error": f"Invalid JSON payload: {e}"}, 400)

        url = data.get("url", "").strip()
        lang = data.get("language", "en").strip()
        max_vocab = data.get("max_vocab", "15")
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
                logger.info(f"Task {task_id}: Processing started for URL: {url} (lang={lang}, max_vocab={max_vocab})")
                res = process_video(url, language=lang, max_vocab=max_vocab, progress_cb=cb)
                with TASKS_LOCK:
                    t = TASKS.get(task_id)
                    if t:
                        t["status"] = "completed"
                        t["percent"] = 100
                        t["step"] = "Hoàn tất"
                        t["result"] = res
                logger.info(f"Task {task_id}: Processing completed successfully! Slug: {res.get('slug')}")
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"Task {task_id}: Video processing failed: {e}\n{tb}")
                with TASKS_LOCK:
                    t = TASKS.get(task_id)
                    if t:
                        t["status"] = "error"
                        t["error"] = str(e)
                        t["traceback"] = tb
                        t["logs"].append(f"❌ Lỗi: {str(e)}")
                        t["logs"].append("💡 Chi tiết lỗi đã được lưu vào nhật ký toolev.log. Bạn có thể nhấn 'Xem nhật ký' để kiểm tra.")

        thread = threading.Thread(target=worker, daemon=True, name=f"TaskWorker-{task_id[:8]}")
        thread.start()

        return self.send_json({"task_id": task_id, "status": "running"})


def run_server(port=8000, open_browser=False):
    for p in range(port, port + 10):
        try:
            server_address = ("", p)
            httpd = ThreadedHTTPServer(server_address, ToolEVRequestHandler)
            print(f"🚀 ToolEV server running at: http://localhost:{p}/")
            print(f"👉 Mở trình duyệt: http://localhost:{p}/all-video.html")
            logger.info(f"ToolEV server running at: http://localhost:{p}/")
            if open_browser:
                import webbrowser
                url = f"http://localhost:{p}/all-video.html"
                threading.Timer(1.2, lambda: webbrowser.open(url)).start()
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                logger.info("Stopping server (KeyboardInterrupt)...")
                print("\nStopping server...")
                httpd.server_close()
            return
        except OSError as e:
            if p == port + 9:
                print(f"[LỖI] Không thể mở cổng mạng: {e}")
                raise


if __name__ == "__main__":
    port = 8000
    should_open = "--open" in sys.argv
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port = int(arg)
    run_server(port, open_browser=should_open)

