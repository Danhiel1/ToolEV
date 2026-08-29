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
VENV_PYTHON = SCRIPTS_DIR / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = SCRIPTS_DIR / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


def slugify(text: str, max_len: int = 50) -> str:
    text = re.sub(r'[^\w\s-]', '', text).strip()
    text = re.sub(r'[\s-]+', '_', text)
    slug = text[:max_len].strip('_')
    return slug if slug else "lesson_video"


def run_cmd(cmd, cwd=None):
    proc = subprocess.run(
        cmd,
        cwd=cwd or str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return proc.returncode, proc.stdout, proc.stderr


def process_video(url: str, output_dir: str = None, language: str = "en", progress_cb=None) -> dict:
    def report(percent: int, step_text: str, log_line: str = ""):
        if progress_cb:
            progress_cb(percent, step_text, log_line)
        sys.stderr.write(f"[{percent}%] {step_text} - {log_line}\n")
        sys.stderr.flush()

    out_root = Path(output_dir or DEFAULT_OUTPUT_DIR)
    out_root.mkdir(parents=True, exist_ok=True)

    report(5, "Khởi động", f"Đang kiểm tra thông tin URL: {url}")

    # 1. Fetch metadata using yt-dlp
    code, stdout, stderr = run_cmd([
        "yt-dlp", "--no-playlist", "--dump-json", "--skip-download", url
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

    # 2. Try YouTube Auto-captions first
    if is_youtube:
        report(25, "Bóc tách phụ đề", "Đang kiểm tra phụ đề gốc YouTube...")
        orig_prefix = str(slug_dir / "yt_orig")
        run_cmd([
            "yt-dlp", "--no-playlist", "--skip-download",
            "--write-auto-subs", "--sub-langs", ".*-orig", "--sub-format", "json3",
            "--output", f"{orig_prefix}.%(ext)s", url
        ])

        found_json3 = list(slug_dir.glob("yt_orig*.json3"))
        if found_json3:
            orig_json = found_json3[0]
            report(35, "Chuyển đổi phụ đề", f"Phát hiện phụ đề gốc {orig_json.name}")
            
            # Run yt_transcript.py
            yt_script = str(SCRIPTS_DIR / "yt_transcript.py")
            code, cap_out, cap_err = run_cmd([
                str(VENV_PYTHON), yt_script, str(orig_json)
            ])
            
            if code == 0 and cap_out.strip():
                part_0 = parts_dir / "part_000_transcript.json"
                with open(part_0, "w", encoding="utf-8") as fp:
                    fp.write(cap_out)
                use_yt_caption = True
                youtube_only = True
                report(50, "Phụ đề hoàn tất", "Đã lấy transcript từ caption gốc YouTube.")
            
            # Clean raw json3 files
            for jf in found_json3:
                try:
                    jf.unlink()
                except Exception:
                    pass

    # 3. Fallback to Downloading video + Whisper local
    if not use_yt_caption:
        report(30, "Tải video", "Không có caption gốc, đang tải file video/audio...")
        video_target = slug_dir / "video.mp4"
        
        # Download media + thumbnail
        dl_cmd = [
            "yt-dlp",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--write-thumbnail", "--convert-thumbnails", "jpg",
            "--output", str(slug_dir / "video.%(ext)s"),
            "--output", f"thumbnail:{slug_dir}/thumb.%(ext)s",
            "--no-playlist", url
        ]
        code, stdout, stderr = run_cmd(dl_cmd)
        if not video_target.exists():
            raise RuntimeError(f"Tải video thất bại: {stderr}")

        report(50, "Whisper Local STT", "Đang chạy mô hình AI nhận diện giọng nói (Whisper)...")
        transcribe_script = str(SCRIPTS_DIR / "transcribe.py")
        code, t_out, t_err = run_cmd([
            str(VENV_PYTHON), transcribe_script, str(video_target),
            "--language", language
        ])
        if code != 0 or not t_out.strip():
            raise RuntimeError(f"Lỗi Whisper STT: {t_err}")

        part_0 = parts_dir / "part_000_transcript.json"
        with open(part_0, "w", encoding="utf-8") as fp:
            fp.write(t_out)
        report(70, "STT hoàn tất", "Đã trích xuất transcript thành công qua Whisper.")

    else:
        # For youtube-only, download thumbnail only
        report(60, "Tải Thumbnail", "Đang tải ảnh thumbnail cho bài học...")
        run_cmd([
            "yt-dlp", "--no-playlist", "--skip-download",
            "--write-thumbnail", "--convert-thumbnails", "jpg",
            "--output", f"thumbnail:{slug_dir}/thumb.%(ext)s", url
        ])

    # 4. Generate IELTS Listening Questions
    report(80, "Biên soạn câu hỏi", "Đang tạo bộ câu hỏi IELTS Listening...")
    from generate_ielts import generate_ielts_for_slug
    ielts_data = generate_ielts_for_slug(
        str(slug_dir),
        title=title,
        youtube_id=video_id if youtube_only else None
    )

    report(100, "Hoàn tất!", f"Đã tạo thành công bài học '{title}' với {ielts_data.get('total', 0)} câu hỏi IELTS.")

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
