#!/usr/bin/env python3
"""
faster-whisper STT — segment-level transcript → JSON SCHEMA CHUNG ra stdout.

App (all-video.html) chỉ đọc `segments` + `duration`, nên không xuất word-level.

Usage:
    python transcribe.py <audio_path> [--language vi] [--model small]
                         [--device cpu] [--compute int8]

In ra stdout DUY NHẤT 1 dòng JSON:
    {"text", "duration", "segments":[{"text","start","end"}]}

Mọi log/diagnostic đi qua stderr để stdout sạch JSON cho Node parse.

AUTO-SPLIT: Nếu audio dài hơn SPLIT_THRESHOLD_SEC (mặc định 600s = 10 phút),
tự động cắt thành các part SPLIT_PART_SEC (mặc định 300s = 5 phút) rồi ghép
kết quả lại — timestamps được offset theo từng part.
"""
import sys
import io
import json
import argparse
import os
import re
import subprocess
import tempfile

# Windows mặc định cp1252 → ép UTF-8 để tiếng Việt có dấu không hỏng.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

SPLIT_THRESHOLD_SEC = 600   # > 10 phút thì split
SPLIT_PART_SEC      = 300   # mỗi part 5 phút
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VENV_SITE = BASE_DIR / "scripts" / ".venv" / "Lib" / "site-packages"
if VENV_SITE.is_dir() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

try:
    from logger import get_logger
    logger = get_logger("transcribe")
except Exception:
    import logging
    logger = logging.getLogger("toolev.transcribe")


def log(msg):
    try:
        if "❌" in msg or "lỗi" in msg.lower() or "thất bại" in msg.lower():
            logger.error(msg)
        elif "⚠️" in msg:
            logger.warning(msg)
        else:
            logger.info(msg)
    except Exception:
        pass
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_duration_ffprobe(path: str) -> float:
    """Lấy duration (giây) bằng ffprobe. Trả về 0.0 nếu lỗi."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", path,
            ],
            stderr=subprocess.DEVNULL,
            **kwargs
        )
        info = json.loads(out)
        return float(info.get("format", {}).get("duration", 0.0))
    except Exception as e:
        log(f"[ffprobe] không đọc được duration: {e}")
        return 0.0


def split_audio_ffmpeg(path: str, part_sec: int, tmp_dir: str) -> list[tuple[str, float]]:
    """
    Cắt file audio thành các đoạn part_sec giây bằng ffmpeg -ss/-t.
    Trả về list[(part_path, offset_sec)] theo thứ tự.
    """
    duration = get_duration_ffprobe(path)
    parts = []
    start = 0.0
    idx = 0
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    while start < duration:
        out_path = os.path.join(tmp_dir, f"part_{idx:03d}.wav")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(part_sec),
            "-i", path,
            "-ar", "16000",   # Whisper thích 16kHz
            "-ac", "1",
            out_path,
        ]
        log(f"[split] part {idx}: {start:.1f}s → {start + part_sec:.1f}s → {out_path}")
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kwargs)
        if result.returncode != 0:
            log(f"[split] ffmpeg lỗi part {idx}: {result.stderr.decode(errors='replace')}")
            break
        parts.append((out_path, start))
        start += part_sec
        idx += 1
    return parts


def transcribe_file(
    model,
    path: str,
    lang,
    offset: float = 0.0,
    total_audio_dur: float = 0.0,
    progress_cb=None
) -> dict:
    """
    Chạy faster-whisper trên 1 file, trả về dict chuẩn với timestamps đã offset.
    Tối ưu siêu tốc: beam_size=1 (greedy), không lặp ảo condition_on_previous_text=False.
    Cập nhật tiến trình từng câu thời gian thực qua progress_cb (50% -> 70%).
    """
    import time
    log(f"[faster-whisper] transcribe {path} (offset={offset:.1f}s, beam_size=1)")
    try:
        segments, info = model.transcribe(
            path,
            language=lang,
            word_timestamps=False,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
        )
    except Exception as e:
        log(f"[faster-whisper] ❌ Lỗi khi khởi tạo transcribe file: {e}")
        raise RuntimeError(f"Whisper transcribe thất bại: {e}")

    file_dur = float(getattr(info, "duration", 0.0) or 0.0)
    dur_for_progress = total_audio_dur if total_audio_dur > 0 else (file_dur or 1.0)

    segs = []
    text_parts = []
    last_report_time = 0.0

    for seg in segments:
        seg_text = (seg.text or "").strip()
        if seg_text:
            text_parts.append(seg_text)
            seg_start = round(float(seg.start) + offset, 3)
            seg_end = round(float(seg.end) + offset, 3)
            segs.append({
                "text": seg_text,
                "start": seg_start,
                "end": seg_end,
            })

            # Báo cáo tiến trình thời gian thực từng câu lên modal (dải 50% -> 70%)
            if progress_cb:
                now = time.time()
                if now - last_report_time >= 0.6:  # Cập nhật mỗi 0.6s
                    pct_ratio = min(1.0, seg_end / dur_for_progress)
                    overall_pct = 50 + int(pct_ratio * 20)
                    disp_text = seg_text if len(seg_text) <= 36 else seg_text[:33] + "..."
                    try:
                        progress_cb(
                            overall_pct,
                            "Whisper Local STT",
                            f"Đang nhận diện: {int(seg_end)}s / {int(dur_for_progress)}s ({int(pct_ratio * 100)}%) - \"{disp_text}\""
                        )
                    except Exception:
                        pass
                    last_report_time = now

    # Cleanup segment boundaries — sửa từ bị vướng giữa 2 câu liền kề
    segs = segment_boundary_cleanup(segs)

    return {
        "text":     " ".join(s["text"] for s in segs).strip(),
        "duration": round(file_dur, 3),
        "segments": segs,
    }


def segment_boundary_cleanup(segs: list[dict]) -> list[dict]:
    """
    Sửa lỗi Whisper segment boundary: từ cuối câu trước bị dính/trùng lặp
    vào đầu câu sau (bleed-over), hoặc timestamps chồng lấn.

    Xử lý:
    1. Fix timestamp overlap — end[i] > start[i+1] → cắt end[i] = start[i+1]
    2. Deduplicate trailing/leading words — nếu 1-3 từ cuối câu A trùng khớp
       với 1-3 từ đầu câu B thì xóa phần trùng ở đầu câu B (giữ câu A nguyên)
    3. Loại bỏ segment rỗng sau cleanup
    4. Merge segment quá ngắn (< 2 từ, < 0.5s) vào câu liền kề
    """
    if not segs or len(segs) < 2:
        return segs

    cleaned = []
    for s in segs:
        cleaned.append({**s})  # shallow copy

    # --- Pass 0: Collapse internal repetitive phrases in segments ---
    for s in cleaned:
        txt = s.get("text", "")
        # Thu gọn thẻ ngoặc lặp lại: [music] [music] -> [music]
        txt = re.sub(r'(\[[^\]]+\])(\s*\1)+', r'\1', txt, flags=re.IGNORECASE)
        # Thu gọn câu lặp 3+ lần: "playing in background, playing in background" -> "playing in background"
        txt = re.sub(r'(\b[\w\s]{4,30}?\b)(?:,\s*\1|\s+\1){2,}', r'\1', txt, flags=re.IGNORECASE)
        s["text"] = txt.strip()

    # --- Pass 1: Fix timestamp overlap ---
    for i in range(len(cleaned) - 1):
        if cleaned[i]["end"] > cleaned[i + 1]["start"]:
            cleaned[i]["end"] = cleaned[i + 1]["start"]

    # --- Pass 2: Deduplicate trailing/leading bleed-over ---
    def normalize(w):
        return re.sub(r'[^\w]', '', w).lower()

    i = 0
    while i < len(cleaned) - 1:
        words_a = cleaned[i]["text"].split()
        words_b = cleaned[i + 1]["text"].split()

        # Kiểm tra 1-3 từ cuối câu A có trùng với 1-3 từ đầu câu B không
        max_check = min(3, len(words_a), len(words_b))
        overlap_len = 0
        for k in range(1, max_check + 1):
            tail_a = [normalize(w) for w in words_a[-k:]]
            head_b = [normalize(w) for w in words_b[:k]]
            if tail_a == head_b and all(len(w) > 0 for w in tail_a):
                overlap_len = k

        if overlap_len > 0:
            # Xóa phần trùng ở đầu câu B, giữ câu A nguyên
            new_text_b = " ".join(words_b[overlap_len:]).strip()
            if new_text_b:
                cleaned[i + 1]["text"] = new_text_b
            else:
                # Câu B chỉ toàn phần trùng → xóa hẳn segment B
                cleaned.pop(i + 1)
                continue
        i += 1

    # --- Pass 3: Merge segment quá ngắn (<2 từ, <0.5s) vào câu liền kề ---
    merged = []
    for s in cleaned:
        txt = s["text"].strip()
        if not txt:
            continue
        word_count = len(txt.split())
        seg_dur = s["end"] - s["start"]

        if merged and word_count < 2 and seg_dur < 0.5:
            # Nối vào câu trước
            merged[-1]["text"] = merged[-1]["text"].rstrip() + " " + txt
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)

    return merged


def merge_results(parts: list[dict], total_duration: float, source: str) -> dict:
    """Ghép nhiều kết quả part thành 1 output cuối."""
    all_segs  = []
    all_text  = []
    for p in parts:
        all_segs.extend(p["segments"])
        if p["text"]:
            all_text.append(p["text"])

    # Apply boundary cleanup across merged parts
    all_segs = segment_boundary_cleanup(all_segs)

    return {
        "text":     " ".join(s["text"] for s in all_segs).strip(),
        "duration": round(total_duration, 3),
        "segments": all_segs,
        "source":   source,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Main / Direct API
# ---------------------------------------------------------------------------

def is_cuda_available() -> bool:
    """
    Kiểm tra xem hệ thống có GPU NVIDIA và ĐẦY ĐỦ thư viện DLL CUDA (cublas64_12.dll) không.
    Ngăn chặn tuyệt đối hiện tượng Windows treo ngầm tiến trình khi thiếu DLL.
    """
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            # Ngăn chặn Windows hiện hộp thoại báo thiếu DLL làm treo tiến trình daemon
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
            h = ctypes.windll.kernel32.LoadLibraryW("cublas64_12.dll")
            if h:
                ctypes.windll.kernel32.FreeLibrary(h)
                return True
            return False
        except Exception:
            return False
    return True


def _load_whisper_model(model_name: str, device: str, compute: str):
    """
    Nạp WhisperModel với fallback: thử CUDA trước (nếu đủ DLL), rồi CPU.
    Tối ưu hóa đa luồng CPU (cpu_threads = số core CPU).
    Nếu model gốc thất bại, tự động thử model nhẹ hơn (base -> tiny).
    Trả về (model, actual_model_name, device_used).
    """
    import os
    from faster_whisper import WhisperModel

    dev = device
    if dev in ("auto", "cuda"):
        if is_cuda_available():
            dev = "cuda"
        else:
            if dev == "cuda":
                log("[faster-whisper] ⚠️ CUDA được yêu cầu nhưng thiếu cublas64_12.dll → Dùng CPU.")
            else:
                log("[faster-whisper] Chưa cài DLL CUDA (cublas64_12.dll) → Tự động chạy CPU đa luồng.")
            dev = "cpu"

    # Danh sách model thử fallback: model gốc → nhẹ hơn dần
    FALLBACK_MODELS = [model_name]
    if model_name not in ("tiny", "tiny.en"):
        if "large" in model_name.lower():
            FALLBACK_MODELS.extend(["medium", "small", "base", "tiny"])
        elif "medium" in model_name.lower():
            FALLBACK_MODELS.extend(["small", "base", "tiny"])
        elif "small" in model_name.lower():
            FALLBACK_MODELS.extend(["base", "tiny"])
        elif "base" in model_name.lower():
            FALLBACK_MODELS.append("tiny")

    cpu_cores = max(4, os.cpu_count() or 4)

    for m_name in FALLBACK_MODELS:
        if dev == "cuda":
            candidate_types = [compute] if compute != "auto" else ["int8", "float16", "int8_float16", "float32"]
            for c_type in candidate_types:
                try:
                    log(f"[faster-whisper] Thử nạp model={m_name} trên CUDA ({c_type})...")
                    m = WhisperModel(m_name, device="cuda", compute_type=c_type)
                    log(f"[faster-whisper] ✅ GPU CUDA ({c_type}) hoạt động tốt!")
                    return m, m_name, "cuda"
                except Exception as e:
                    log(f"[faster-whisper] ⚠️ CUDA ({c_type}) lỗi ({e}) → Chuyển sang CPU.")
                    break

        # CPU fallback với đa luồng tối đa
        cpu_name = m_name
        if "large" in cpu_name.lower():
            cpu_name = "base"  # large trên CPU quá nặng, ưu tiên base
        try:
            log(f"[faster-whisper] Nạp model={cpu_name} trên CPU (int8, {cpu_cores} luồng)...")
            m = WhisperModel(cpu_name, device="cpu", compute_type="int8", cpu_threads=cpu_cores)
            log(f"[faster-whisper] ✅ Nạp thành công trên CPU (int8) model={cpu_name}")
            return m, cpu_name, "cpu"
        except MemoryError:
            log(f"[faster-whisper] ❌ Hết bộ nhớ khi nạp model={cpu_name}, thử model nhỏ hơn...")
            continue
        except Exception as e:
            log(f"[faster-whisper] ❌ Lỗi nạp model={cpu_name}: {e}")
            continue

    raise RuntimeError(
        f"Không thể nạp bất kỳ Whisper model nào (thử: {', '.join(FALLBACK_MODELS)}). "
        f"Vui lòng kiểm tra cài đặt faster-whisper và dung lượng RAM."
    )


def transcribe_audio(
    audio_path: str,
    language: str = "en",
    model_name: str = "base",
    device: str = "auto",
    compute: str = "auto",
    progress_cb=None,
) -> dict:
    """
    Chạy nhận diện giọng nói faster-whisper trực tiếp trong tiến trình.
    Hỗ trợ auto-split audio nếu vượt ngưỡng SPLIT_THRESHOLD_SEC.
    Tự động fallback model nhỏ hơn nếu model chính thất bại.
    Áp dụng segment boundary cleanup để sửa từ bị vướng giữa các câu.
    Cập nhật tiến trình từng câu theo thời gian thực qua progress_cb.
    """
    try:
        from faster_whisper import WhisperModel  # noqa: F401 — validate import
    except ImportError:
        raise RuntimeError(
            "Thiếu thư viện faster-whisper. Vui lòng cài đặt: pip install faster-whisper"
        )

    # --- Nạp model với fallback ---
    try:
        model, actual_model_name, dev = _load_whisper_model(
            model_name, device, compute
        )
    except RuntimeError as e:
        raise RuntimeError(f"Whisper model load thất bại: {e}")

    lang = None if language in ("", "auto") else language
    source = f"faster-whisper:{actual_model_name}"

    total_duration = get_duration_ffprobe(audio_path)
    log(f"[faster-whisper] audio duration: {total_duration:.1f}s")

    try:
        if total_duration > SPLIT_THRESHOLD_SEC:
            log(
                f"[faster-whisper] audio > {SPLIT_THRESHOLD_SEC}s → "
                f"tự động cắt thành part {SPLIT_PART_SEC}s"
            )
            with tempfile.TemporaryDirectory(prefix="whisper_split_") as tmp_dir:
                parts_info = split_audio_ffmpeg(audio_path, SPLIT_PART_SEC, tmp_dir)
                if not parts_info:
                    log("[faster-whisper] split thất bại — thử transcribe nguyên file.")
                    result_parts = [transcribe_file(
                        model, audio_path, lang,
                        offset=0.0,
                        total_audio_dur=total_duration,
                        progress_cb=progress_cb
                    )]
                else:
                    log(f"[faster-whisper] tổng {len(parts_info)} part, bắt đầu transcribe từng part…")
                    result_parts = []
                    for part_path, offset in parts_info:
                        part_result = transcribe_file(
                            model, part_path, lang,
                            offset=offset,
                            total_audio_dur=total_duration,
                            progress_cb=progress_cb
                        )
                        log(
                            f"[faster-whisper] part offset={offset:.1f}s: "
                            f"{len(part_result['segments'])} câu"
                        )
                        result_parts.append(part_result)

            result = merge_results(result_parts, total_duration, source)
        else:
            r = transcribe_file(
                model, audio_path, lang,
                offset=0.0,
                total_audio_dur=total_duration,
                progress_cb=progress_cb
            )
            result = {**r, "source": source}
            if result["duration"] == 0.0 and total_duration > 0:
                result["duration"] = round(total_duration, 3)

        if progress_cb:
            try:
                progress_cb(
                    70,
                    "Whisper Local STT",
                    f"Hoàn tất nhận diện giọng nói: {len(result.get('segments', []))} câu."
                )
            except Exception:
                pass

    except MemoryError:
        raise RuntimeError(
            f"Hết bộ nhớ khi chạy Whisper (model={actual_model_name}). "
            f"Hãy thử model nhỏ hơn hoặc video ngắn hơn."
        )
    except RuntimeError:
        raise  # propagate RuntimeError từ transcribe_file
    except Exception as e:
        raise RuntimeError(
            f"Whisper STT gặp lỗi không mong đợi: {type(e).__name__}: {e}"
        )

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--language", default="en")
    ap.add_argument("--model",   default="large-v3-turbo")
    ap.add_argument("--device",  default="auto")    # auto|cpu|cuda
    ap.add_argument("--compute", default="auto")    # auto|int8|float16|float32|int8_float32
    args = ap.parse_args()

    result = transcribe_audio(
        args.audio,
        language=args.language,
        model_name=args.model,
        device=args.device,
        compute=args.compute
    )

    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    log(
        f"[faster-whisper] xong: {len(result['segments'])} câu, {result['duration']}s"
    )


if __name__ == "__main__":
    main()