#!/usr/bin/env python3
"""
Generate IELTS Listening questions from transcript JSON.
Supports both offline NLP heuristic generation and optional LLM (Gemini API) if GEMINI_API_KEY is present.
"""
import os
import sys
import json
import re
import random
import glob
import urllib.request
import urllib.error
from datetime import datetime

try:
    from vocab_service import extract_key_vocabulary
except Exception:
    extract_key_vocabulary = None

try:
    from logger import get_logger
    logger = get_logger("generate_ielts")
except Exception:
    import logging
    logger = logging.getLogger("toolev.generate_ielts")


# Windows encoding fix
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
    "gonna", "wanna", "gotta", "yeah", "okay", "like", "know", "well", "actually", "basically"
}


def clean_text(text: str) -> str:
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'>>', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def load_transcript(slug_dir: str):
    parts = sorted(glob.glob(os.path.join(slug_dir, "parts", "*_transcript.json")))
    segments = []
    source = "faster-whisper"
    
    for f in parts:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
                if "source" in d:
                    source = d["source"]
                for s in d.get("segments", []):
                    txt = clean_text(s.get("text", ""))
                    if txt:
                        segments.append({
                            "text": txt,
                            "start": float(s.get("start", 0)),
                            "end": float(s.get("end", 0))
                        })
        except Exception as e:
            sys.stderr.write(f"Error loading {f}: {e}\n")
            
    return segments, source


def combine_into_sentences(segments, max_dur=15.0):
    sentences = []
    current_text = []
    start_t = 0.0
    end_t = 0.0
    
    for seg in segments:
        txt = seg["text"]
        if not current_text:
            start_t = seg["start"]
        current_text.append(txt)
        end_t = seg["end"]
        
        full = " ".join(current_text)
        if full.endswith((".", "!", "?")) or (end_t - start_t >= max_dur):
            sentences.append({
                "text": full,
                "start": round(start_t, 2),
                "end": round(end_t, 2)
            })
            current_text = []
            
    if current_text:
        sentences.append({
            "text": " ".join(current_text),
            "start": round(start_t, 2),
            "end": round(end_t, 2)
        })
        
    return sentences


def generate_with_gemini(api_key: str, title: str, slug: str, youtube_id: str, segments: list, source: str):
    transcript_text = "\n".join([f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}" for s in segments[:100]])
    
    prompt = f"""You are an expert IELTS Listening exam writer.
Generate exactly 8-10 IELTS Listening questions based strictly on this video transcript.

Video Title: "{title}"
Transcript:
{transcript_text}

Question Requirements:
- Mix question types:
  1. "multiple_choice" (options array with "A. ...", "B. ...", "C. ...", and exact answer string matching one option)
  2. "sentence_completion" (question with "____", word_limit in Vietnamese like "CHỈ MỘT TỪ" or "KHÔNG QUÁ HAI TỪ", exact answer extracted from audio)
  3. "short_answer" (direct question, short answer from audio, word_limit in Vietnamese)
- Questions must be in chronological order of appearance in the audio.
- Include precise "start" and "end" float timestamps in seconds where the answer is heard.
- Include short "explanation" quoting the speech.
- Output MUST be valid JSON only matching this schema:
{{
  "title": "{title}",
  "slug": "{slug}",
  "level": "IELTS Listening",
  "total": 10,
  "questions": [
    {{
      "no": 1,
      "type": "multiple_choice",
      "question": "What is ...?",
      "options": ["A. Option 1", "B. Option 2", "C. Option 3"],
      "answer": "B. Option 2",
      "word_limit": null,
      "start": 1.5,
      "end": 6.8,
      "explanation": "..."
    }}
  ]
}}
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        cand_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(cand_text)
        if youtube_id:
            data["youtube_id"] = youtube_id
        data["source_transcript"] = source
        data["created_at"] = datetime.now().isoformat()
        return data


def generate_offline_heuristic(title: str, slug: str, youtube_id: str, segments: list, source: str) -> dict:
    sentences = combine_into_sentences(segments)
    
    # Filter sentences with decent length
    valid_sentences = [s for s in sentences if len(s["text"].split()) >= 6]
    if len(valid_sentences) < 4:
        valid_sentences = sentences if sentences else [{"text": title, "start": 0.0, "end": 5.0}]
        
    target_count = min(10, max(3, len(valid_sentences)))
    step = len(valid_sentences) / target_count
    selected = [valid_sentences[int(i * step)] for i in range(target_count)]
    
    all_words = []
    for s in valid_sentences:
        for w in re.findall(r'\b[a-zA-Z]{4,}\b', s["text"]):
            wl = w.lower()
            if wl not in STOPWORDS:
                all_words.append(w)
                
    distractor_pool = list(set(all_words))
    if len(distractor_pool) < 10:
        distractor_pool.extend(["technology", "experience", "education", "development", "information", "practice", "community", "strategy", "language", "method"])

    questions = []
    
    for idx, item in enumerate(selected):
        s_text = item["text"]
        start_t = item["start"]
        end_t = item["end"]
        words = re.findall(r'\b[a-zA-Z0-9\'-]+\b', s_text)
        
        # Pick candidate keywords
        cand_words = [w for w in words if w.lower() not in STOPWORDS and len(w) >= 3 and not w.isdigit()]
        if not cand_words:
            cand_words = [w for w in words if len(w) >= 3] or [words[0] if words else "lesson"]
            
        target_word = cand_words[len(cand_words) // 2]
        
        # Cycle through question types: sentence_completion, multiple_choice, short_answer
        q_type_idx = idx % 3
        
        if q_type_idx == 0:
            # Sentence completion
            pattern = re.compile(re.escape(target_word), re.IGNORECASE)
            masked_sentence = pattern.sub("____", s_text, count=1)
            
            questions.append({
                "no": idx + 1,
                "type": "sentence_completion",
                "question": f"Hoàn thành câu sau từ đoạn nghe: \"{masked_sentence}\"",
                "options": [],
                "answer": target_word,
                "word_limit": "CHỈ MỘT TỪ",
                "start": start_t,
                "end": end_t,
                "explanation": f"Từ audio trích dẫn: \"{s_text}\""
            })
            
        elif q_type_idx == 1:
            # Multiple choice
            other_options = [w for w in distractor_pool if w.lower() != target_word.lower()]
            sampled_distractors = random.sample(other_options, min(2, len(other_options)))
            
            opts_raw = [target_word] + sampled_distractors
            random.shuffle(opts_raw)
            
            letters = ["A", "B", "C"]
            options = [f"{letters[i]}. {opts_raw[i]}" for i in range(len(opts_raw))]
            
            correct_idx = opts_raw.index(target_word)
            correct_answer = options[correct_idx]
            
            questions.append({
                "no": idx + 1,
                "type": "multiple_choice",
                "question": f"Theo người nói trong đoạn này, từ hoặc nội dung nào được nhắc đến khi nói về: \"{s_text[:70]}...\"?",
                "options": options,
                "answer": correct_answer,
                "word_limit": None,
                "start": start_t,
                "end": end_t,
                "explanation": f"Trong đoạn nói: \"{s_text}\""
            })
            
        else:
            # Short answer
            questions.append({
                "no": idx + 1,
                "type": "short_answer",
                "question": f"Từ khóa quan trọng xuất hiện trong đoạn nói \"{s_text[:60]}...\" là gì?",
                "options": [],
                "answer": target_word,
                "word_limit": "CHỈ MỘT TỪ",
                "start": start_t,
                "end": end_t,
                "explanation": f"Chi tiết trong audio: \"{s_text}\""
            })
            
    result = {
        "title": title,
        "slug": slug,
        "source_transcript": source,
        "level": "IELTS Listening",
        "total": len(questions),
        "created_at": datetime.now().isoformat(),
        "questions": questions
    }
    
    if youtube_id:
        result["youtube_id"] = youtube_id
        
    return result


def generate_ielts_for_slug(slug_dir: str, title: str = None, youtube_id: str = None, max_vocab: int = 15) -> dict:
    slug = os.path.basename(os.path.normpath(slug_dir))
    if not title:
        title = slug.replace("_", " ")

    segments, source = load_transcript(slug_dir)
    if not segments:
        logger.warning(f"No transcript segments found in {slug_dir}/parts")

    api_key = os.environ.get("GEMINI_API_KEY")
    result = None

    if api_key and segments:
        try:
            logger.info(f"Generating IELTS questions using Gemini API for '{title}'...")
            result = generate_with_gemini(api_key, title, slug, youtube_id, segments, source)
        except Exception as e:
            logger.warning(f"Gemini API generation failed ({e}), falling back to offline heuristic...")

    if not result:
        logger.info(f"Generating IELTS questions with offline NLP engine for '{title}'...")
        result = generate_offline_heuristic(title, slug, youtube_id, segments, source)

    if segments and extract_key_vocabulary and not result.get("vocabulary"):
        try:
            logger.info(f"Extracting {max_vocab} key vocabulary items for '{title}'...")
            result["vocabulary"] = extract_key_vocabulary(segments, max_words=max_vocab)
        except Exception as e:
            logger.error(f"Vocab extraction error: {e}", exc_info=True)
            result["vocabulary"] = []

    out_file = os.path.join(slug_dir, "ielts_listening.json")
    with open(out_file, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)

    logger.info(f"Generated {len(result.get('questions', []))} IELTS questions & {len(result.get('vocabulary', []))} vocabulary items -> {out_file}")
    return result



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_ielts.py <slug_dir> [title] [youtube_id]")
        sys.exit(1)
        
    s_dir = sys.argv[1]
    s_title = sys.argv[2] if len(sys.argv) > 2 else None
    s_yt_id = sys.argv[3] if len(sys.argv) > 3 else None
    
    data = generate_ielts_for_slug(s_dir, s_title, s_yt_id)
    print(json.dumps(data, ensure_ascii=False))
