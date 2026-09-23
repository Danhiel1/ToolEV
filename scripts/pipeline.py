#!/usr/bin/env python3
"""
Unified Video to IELTS Lesson Pipeline for ToolEV.
Processes YouTube / online video URLs into ready-to-study IELTS lessons.
"""
import os
import sys
import json
import re
import glob
import shutil
import subprocess
from pathlib import Path

# Ensure UTF-8 IO
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
BIN_DIR = BASE_DIR / "bin"
VENV_DIR = SCRIPTS_DIR / ".venv"
VENV_SITE = VENV_DIR / "Lib" / "site-packages"

# Tự động nạp bin/ (chứa ffmpeg/ffprobe) vào PATH
if BIN_DIR.is_dir():
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

# Tự động nạp Scripts của .venv vào PATH nếu có
if (VENV_DIR / "Scripts").is_dir():
    os.environ["PATH"] = str(VENV_DIR / "Scripts") + os.pathsep + os.environ.get("PATH", "")

# Tự động nạp thư viện AI (faster-whisper, ctranslate2) từ .venv nếu chạy ngoài venv
if VENV_SITE.is_dir() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

# Tự động nhận diện lệnh yt-dlp (trực tiếp hoặc qua python -m yt_dlp)
YTDLP_CMD = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]

try:
    from logger import get_logger
    logger = get_logger("pipeline")
except Exception:
    import logging
    logger = logging.getLogger("toolev.pipeline")


def slugify(text: str, max_len: int = 50) -> str:
    text = re.sub(r'[^\w\s-]', '', text).strip()
    text = re.sub(r'[\s-]+', '_', text)
    slug = text[:max_len].strip('_')
    return slug if slug else "lesson_video"


def run_cmd(cmd, cwd=None):
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    proc = subprocess.run(
        cmd,
        cwd=cwd or str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs
    )
    if proc.returncode != 0 and proc.stderr:
        logger.warning(f"Command returned code {proc.returncode}: {' '.join(str(c) for c in cmd[:3])}... | Error: {proc.stderr[:200].strip()}")
    return proc.returncode, proc.stdout, proc.stderr


def process_video(url: str, output_dir: str = None, language: str = "en", max_vocab = "15", progress_cb=None) -> dict:
    def report(percent: int, step_text: str, log_line: str = ""):
        if progress_cb:
            progress_cb(percent, step_text, log_line)
        logger.info(f"[{percent}%] {step_text} - {log_line}")
        try:
            sys.stderr.write(f"[{percent}%] {step_text} - {log_line}\n")
            sys.stderr.flush()
        except Exception:
            pass

    out_root = Path(output_dir or DEFAULT_OUTPUT_DIR)
    out_root.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== Starting Video Processing: {url} (lang={language}, max_vocab={max_vocab}) ===")

    report(5, "Khởi động", f"Đang kiểm tra thông tin URL: {url}")

    # 1. Fetch metadata using yt-dlp
    code, stdout, stderr = run_cmd(YTDLP_CMD + [
        "--no-playlist", "--dump-json", "--skip-download", url
    ])
    if code != 0 or not stdout.strip():
        raise RuntimeError(f"Không thể lấy thông tin video từ yt-dlp: {stderr}")

    try:
        info = json.loads(stdout.strip().split("\n")[0])
    except Exception as e:
        raise RuntimeError(f"Lỗi parse thông tin video: {e}")

    title = info.get("title", "Video Lesson")
    video_id = info.get("id", "video")
    extractor = info.get("extractor", "").lower()
    duration = info.get("duration", 0)
    is_youtube = ("youtube" in extractor)

    slug = slugify(title)
    if not slug or len(slug) < 3:
        slug = f"yt_{video_id}"

    slug_dir = out_root / slug
    parts_dir = slug_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    report(15, "Phân tích video", f"Tiêu đề: {title} | Slug: {slug}")

    use_yt_caption = False
    youtube_only = False

    # 2. Try YouTube Auto-captions / Subtitles first
    if is_youtube:
        report(25, "Bóc tách phụ đề", "Đang lấy phụ đề gốc YouTube...")
        orig_prefix = str(slug_dir / "yt_orig")
        # CHỈ lấy ngôn ngữ mục tiêu & tiếng Anh: KHÔNG dùng 'all' để tránh bị YouTube 429 Too Many Requests
        target_sub_langs = "en.*,en-orig,en" if language == "en" else f"{language}.*,{language}-orig,en.*,en"
        run_cmd(YTDLP_CMD + [
            "--no-playlist", "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", target_sub_langs,
            "--sub-format", "json3",
            "--output", f"{orig_prefix}.%(ext)s", url
        ])

        found_json3 = list(slug_dir.glob("yt_orig*.json3"))
        if found_json3:
            # Ưu tiên phụ đề gốc hoặc ngôn ngữ mong muốn
            orig_json = found_json3[0]
            for jf in found_json3:
                if "orig" in jf.name or (language and language in jf.name):
                    orig_json = jf
                    break

            report(35, "Chuyển đổi phụ đề", f"Phát hiện phụ đề {orig_json.name}")
            
            try:
                from yt_transcript import convert
                cap_data = convert(str(orig_json))
                if cap_data and cap_data.get("segments"):
                    part_0 = parts_dir / "part_000_transcript.json"
                    with open(part_0, "w", encoding="utf-8") as fp:
                        json.dump(cap_data, fp, ensure_ascii=False, indent=2)
                    use_yt_caption = True
                    youtube_only = True
                    report(50, "Phụ đề hoàn tất", f"Đã lấy {len(cap_data['segments'])} câu từ caption YouTube.")
            except Exception as e:
                report(38, "Phụ đề lỗi", f"Không phân tích được caption: {e}")
            
            # Clean raw json3 files
            for jf in found_json3:
                try:
                    jf.unlink()
                except Exception:
                    pass

    # Tải thumbnail nhanh qua HTTP trực tiếp (chỉ mất ~0.2s)
    report(60, "Tải Thumbnail", "Đang lưu ảnh thumbnail bài học...")
    thumb_target = slug_dir / "thumb.jpg"
    thumb_url = info.get("thumbnail") or (f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" if is_youtube else None)
    if thumb_url and not thumb_target.exists():
        try:
            import urllib.request
            req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp, open(thumb_target, "wb") as fp:
                fp.write(resp.read())
        except Exception:
            pass

    # 3. Fallback to Downloading video + Whisper local (nếu không có caption YouTube)
    if not use_yt_caption:
        report(30, "Tải video", "Không có caption gốc, đang tải file âm thanh/video...")
        video_target = slug_dir / "video.mp4"
        
        # Download media tối ưu (giới hạn 720p để tải nhanh gấp 5 lần 4K/1080p)
        dl_cmd = YTDLP_CMD + [
            "--format", "best[height<=720]/bestvideo[height<=720]+bestaudio/best",
            "--merge-output-format", "mp4",
            "--output", str(video_target),
            "--no-playlist", url
        ]
        code, stdout, stderr = run_cmd(dl_cmd)
        if not video_target.exists():
            raise RuntimeError(f"Tải video thất bại: {stderr}")

        report(50, "Whisper Local STT", "Đang nạp mô hình AI nhận diện giọng nói (Whisper)...")
        try:
            from transcribe import transcribe_audio
            t_data = transcribe_audio(
                str(video_target),
                language=language,
                model_name="base",
                progress_cb=report
            )
        except ImportError as e:
            report(50, "Whisper Local STT", f"❌ Thiếu thư viện: {e}")
            logger.error(f"Whisper ImportError: {e}", exc_info=True)
            raise RuntimeError(f"Thiếu thư viện Whisper: {e}. Hãy chạy: pip install faster-whisper")
        except MemoryError:
            report(50, "Whisper Local STT", "❌ Hết bộ nhớ RAM khi chạy Whisper")
            logger.error("Whisper MemoryError: Hết RAM khi chạy Whisper STT", exc_info=True)
            raise RuntimeError("Hết bộ nhớ khi chạy Whisper. Hãy đóng bớt ứng dụng hoặc dùng video ngắn hơn.")
        except RuntimeError as e:
            report(50, "Whisper Local STT", f"❌ {e}")
            logger.error(f"Whisper RuntimeError: {e}", exc_info=True)
            raise
        except Exception as e:
            report(50, "Whisper Local STT", f"❌ Lỗi không mong đợi: {type(e).__name__}: {e}")
            logger.error(f"Whisper unexpected exception ({type(e).__name__}): {e}", exc_info=True)
            raise RuntimeError(f"Whisper STT gặp lỗi: {type(e).__name__}: {e}")

        if not t_data or not t_data.get("segments"):
            raise RuntimeError("Whisper STT không nhận diện được đoạn âm thanh nào.")

        part_0 = parts_dir / "part_000_transcript.json"
        with open(part_0, "w", encoding="utf-8") as fp:
            json.dump(t_data, fp, ensure_ascii=False, indent=2)
        report(70, "STT hoàn tất", f"Đã trích xuất transcript thành công ({len(t_data['segments'])} câu).")


    # 4. Generate IELTS Listening Questions & Key Vocabulary
    vocab_count = 15
    if str(max_vocab).lower() == "auto":
        if duration <= 180:
            vocab_count = 10
        elif duration <= 600:
            vocab_count = 15
        elif duration <= 1200:
            vocab_count = 20
        else:
            vocab_count = 30
    else:
        try:
            vocab_count = max(5, min(50, int(max_vocab)))
        except Exception:
            vocab_count = 15

    report(80, "Biên soạn bài học", f"Đang tạo câu hỏi IELTS & trích xuất {vocab_count} từ vựng...")
    from generate_ielts import generate_ielts_for_slug
    ielts_data = generate_ielts_for_slug(
        str(slug_dir),
        title=title,
        youtube_id=video_id if youtube_only else None,
        max_vocab=vocab_count
    )

    report(100, "Hoàn tất!", f"Đã tạo bài học '{title}' với {ielts_data.get('total', 0)} câu hỏi IELTS & {len(ielts_data.get('vocabulary', []))} từ vựng.")

    return {
        "slug": slug,
        "title": title,
        "youtube_id": video_id if youtube_only else None,
        "is_youtube_only": youtube_only,
        "questions_count": len(ielts_data.get("questions", [])),
        "path": str(slug_dir)
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <url> [--lang en] [--out output_dir]")
        sys.exit(1)

    video_url = sys.argv[1]
    lang = "en"
    if "--lang" in sys.argv:
        idx = sys.argv.index("--lang")
        if idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1]

    def log_cb(pct, step, msg):
        print(f"[{pct}%] {step}: {msg}")

    try:
        res = process_video(video_url, language=lang, progress_cb=log_cb)
        print("\n🎉 KẾT QUẢ:")
        print(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"\n❌ LỖI: {exc}", file=sys.stderr)
        sys.exit(1)
