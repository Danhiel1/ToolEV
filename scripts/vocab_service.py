#!/usr/bin/env python3
"""
Vocabulary service for ToolEV:
- Word and sentence translation to Vietnamese
- Phonetics (IPA), Part of Speech, definition, examples lookup
- Key vocabulary extraction from transcripts
- Persistent local vocabulary store (saved_vocab.json)
"""
import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error
import threading
from pathlib import Path
from datetime import datetime

# Windows encoding fix
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
CACHE_FILE = OUTPUT_DIR / "dict_cache.json"
SAVED_VOCAB_FILE = OUTPUT_DIR / "saved_vocab.json"

try:
    from logger import get_logger
    logger = get_logger("vocab_service")
except Exception:
    import logging
    logger = logging.getLogger("toolev.vocab_service")

DICT_CACHE = {}
CACHE_LOCK = threading.Lock()

def load_dict_cache():
    global DICT_CACHE
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            with CACHE_LOCK:
                DICT_CACHE = data
            logger.info(f"Loaded {len(DICT_CACHE)} cached dictionary entries from {CACHE_FILE.name}")
        except Exception as e:
            logger.warning(f"Failed to load dictionary cache: {e}")
            with CACHE_LOCK:
                DICT_CACHE = {}

def save_dict_cache():
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with CACHE_LOCK:
            data_copy = dict(DICT_CACHE)
        with open(CACHE_FILE, "w", encoding="utf-8") as fp:
            json.dump(data_copy, fp, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save dictionary cache: {e}")

load_dict_cache()

# Stopwords for filtering out trivial words during vocabulary extraction
COMMON_STOPWORDS = {
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
    "gonna", "wanna", "gotta", "yeah", "okay", "like", "know", "well", "actually", "basically",
    "thing", "things", "people", "said", "say", "saying", "went", "going", "goes", "make", "made",
    "making", "come", "came", "coming", "take", "took", "taking", "look", "looked", "looking",
    "get", "got", "getting", "give", "gave", "giving", "think", "thought", "thinking", "see",
    "saw", "seen", "seeing", "want", "wanted", "wanting", "tell", "told", "telling", "one", "two",
    "first", "second", "third", "also", "even", "really", "much", "many", "good", "great", "way"
}


def clean_word(w: str) -> str:
    return re.sub(r"[^\w\s'-]", "", w).strip()


def translate_with_google(text: str, target_lang: str = "vi") -> tuple[str, list, str]:
    """
    Translates text to Vietnamese using Google Translate web API.
    Returns: (main_translation, list_of_pos_definitions, ipa_or_translit)
    """
    encoded = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&dt=bd&dt=rm&dt=md&q={encoded}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
    main_trans = ""
    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
        main_trans = "".join([part[0] for part in data[0] if part and len(part) > 0 and part[0]]).strip()
        
    definitions = []
    # If single word, data[1] often contains parts of speech & synonym translations
    if len(data) > 1 and data[1] and isinstance(data[1], list):
        for item in data[1]:
            if isinstance(item, list) and len(item) >= 2:
                pos = item[0]
                terms = item[1] if isinstance(item[1], list) else []
                definitions.append({
                    "pos": pos,
                    "meanings": terms[:5]
                })
                
    phonetic = ""
    if len(data) > 0 and isinstance(data[0], list) and len(data[0]) > 0:
        last_seg = data[0][-1]
        if isinstance(last_seg, list) and len(last_seg) >= 4 and last_seg[3]:
            phonetic = str(last_seg[3])
            
    return main_trans, definitions, phonetic


from concurrent.futures import ThreadPoolExecutor, as_completed

_LOOKUP_EXECUTOR = ThreadPoolExecutor(max_workers=16)

def fetch_google_translation_safe(text: str, target_lang: str = "vi") -> tuple[str, list, str]:
    try:
        return translate_with_google(text, target_lang)
    except Exception:
        return text, [], ""

def fetch_free_dictionary(word: str) -> dict:
    """
    Fetches IPA, audio, POS, and english definitions from Free Dictionary API.
    Uses a fast 1.0s timeout to prevent UI lag.
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                entry = data[0]
                ipa = entry.get("phonetic", "")
                audio_url = ""
                for p in entry.get("phonetics", []):
                    if not ipa and p.get("text"):
                        ipa = p.get("text")
                    if not audio_url and p.get("audio"):
                        audio_url = p.get("audio")
                        
                pos_list = []
                for m in entry.get("meanings", []):
                    part_of_speech = m.get("partOfSpeech", "")
                    defs = []
                    for d in m.get("definitions", [])[:2]:
                        defs.append({
                            "definition": d.get("definition", ""),
                            "example": d.get("example", "")
                        })
                    pos_list.append({
                        "pos": part_of_speech,
                        "definitions": defs
                    })
                    
                return {
                    "ipa": ipa,
                    "audio_url": audio_url,
                    "pos_entries": pos_list
                }
    except Exception:
        pass
    return {}

def fetch_dictionary_safe(word: str) -> dict:
    try:
        return fetch_free_dictionary(word)
    except Exception:
        return {}

def lookup_word(query: str, context: str = "") -> dict:
    """
    Comprehensive word lookup with Vietnamese translation, IPA, POS, definition & examples.
    Runs Google translation and Dictionary lookups IN PARALLEL for maximum speed (< 200ms).
    Results are cached in memory and persistent disk cache.
    """
    q_norm = query.strip()
    if not q_norm:
        return {"word": "", "translation": "", "ipa": "", "pos": "", "definitions": []}
        
    cache_key = q_norm.lower()
    with CACHE_LOCK:
        if cache_key in DICT_CACHE:
            cached = dict(DICT_CACHE[cache_key])
            if context and not cached.get("context"):
                cached["context"] = context
            return cached

    is_single_word = len(q_norm.split()) == 1 and bool(re.match(r"^[a-zA-Z'-]+$", q_norm))

    # Chạy song song Google Translate & Free Dictionary API để tối ưu tốc độ
    future_gt = _LOOKUP_EXECUTOR.submit(fetch_google_translation_safe, q_norm, "vi")
    future_dict = _LOOKUP_EXECUTOR.submit(fetch_dictionary_safe, q_norm) if is_single_word else None

    # Lấy kết quả Google Translate
    main_trans, pos_defs, translit = future_gt.result(timeout=4)

    # Lấy kết quả Dictionary API (nếu có, không để block quá 1.0s)
    dict_info = {}
    if future_dict:
        try:
            dict_info = future_dict.result(timeout=1.0) or {}
        except Exception:
            dict_info = {}

    ipa = dict_info.get("ipa") or (f"/{translit}/" if translit else "")
    audio_url = dict_info.get("audio_url", "")
    
    # Primary part of speech
    primary_pos = ""
    if pos_defs:
        primary_pos = pos_defs[0].get("pos", "")
    elif dict_info.get("pos_entries"):
        primary_pos = dict_info["pos_entries"][0].get("pos", "")

    # Sample English definition and example
    sample_en_def = ""
    sample_example = ""
    if dict_info.get("pos_entries"):
        for pe in dict_info["pos_entries"]:
            for d in pe.get("definitions", []):
                if not sample_en_def and d.get("definition"):
                    sample_en_def = d.get("definition")
                if not sample_example and d.get("example"):
                    sample_example = d.get("example")

    result = {
        "word": q_norm,
        "translation": main_trans or q_norm,
        "ipa": ipa,
        "pos": primary_pos,
        "audio_url": audio_url,
        "pos_definitions": pos_defs,
        "en_definition": sample_en_def,
        "example": sample_example or context,
        "context": context,
        "updated_at": int(time.time() * 1000)
    }

    # Save to cache thread-safely
    with CACHE_LOCK:
        DICT_CACHE[cache_key] = result
    save_dict_cache()
    
    return result


def lookup_words_batch(words: list[str]) -> dict[str, dict]:
    """
    Look up multiple words in parallel with high concurrency.
    Returns mapping { word: lookup_result }
    """
    results = {}
    uncached = []

    for w in words:
        clean = w.strip()
        if not clean:
            continue
        k = clean.lower()
        with CACHE_LOCK:
            if k in DICT_CACHE:
                results[k] = dict(DICT_CACHE[k])
            else:
                uncached.append(clean)

    if uncached:
        # Giới hạn tối đa 30 từ mỗi lượt batch để tránh spam
        to_fetch = list(set(uncached))[:30]
        futures = { _LOOKUP_EXECUTOR.submit(lookup_word, w): w.lower() for w in to_fetch }
        for fut in as_completed(futures):
            k = futures[fut]
            try:
                res = fut.result(timeout=4)
                results[k] = res
            except Exception:
                pass

    return results



from concurrent.futures import ThreadPoolExecutor

def extract_key_vocabulary(segments: list, max_words: int = 12) -> list:
    """
    Extracts top high-value vocabulary items from transcript segments with Vietnamese translation.
    Uses multi-threading for fast parallel lookups.
    """
    all_text = " ".join([s.get("text", "") for s in segments])
    # Extract candidate words with length >= 5 or hyphenated compounds
    words_raw = re.findall(r"\b[a-zA-Z]{5,}(?:-[a-zA-Z]+)*\b", all_text)
    
    word_freq = {}
    for w in words_raw:
        wl = w.lower()
        if wl not in COMMON_STOPWORDS and not wl.isdigit() and len(wl) >= 4:
            word_freq[wl] = word_freq.get(wl, 0) + 1

    # Prioritize interesting words: frequency between 1 and 6, length >= 6
    sorted_words = sorted(
        word_freq.keys(),
        key=lambda k: (len(k) >= 6, word_freq[k] >= 2, len(k)),
        reverse=True
    )
    
    selected_words = sorted_words[:max_words]
    
    def process_word(word):
        # Find first occurrence segment for timestamp & sentence context
        matched_seg = None
        for s in segments:
            if re.search(rf"\b{re.escape(word)}\b", s.get("text", ""), re.IGNORECASE):
                matched_seg = s
                break

        context_sentence = matched_seg.get("text", "") if matched_seg else ""
        start_time = float(matched_seg.get("start", 0)) if matched_seg else 0.0
        
        info = lookup_word(word, context=context_sentence)
        return {
            "word": word,
            "translation": info.get("translation", ""),
            "ipa": info.get("ipa", ""),
            "pos": info.get("pos", ""),
            "definition": info.get("en_definition", ""),
            "context": context_sentence,
            "start": round(start_time, 2)
        }

    vocab_list = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(process_word, selected_words)
        vocab_list = list(results)

    return vocab_list



class VocabStore:
    """
    Manages user-saved vocabulary in output/saved_vocab.json.
    """
    @staticmethod
    def get_all(filter_status: str = None, filter_slug: str = None) -> list:
        SAVED_VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not SAVED_VOCAB_FILE.exists():
            return []
        try:
            with open(SAVED_VOCAB_FILE, "r", encoding="utf-8") as fp:
                items = json.load(fp)
                if not isinstance(items, list):
                    items = []
        except Exception:
            items = []

        if filter_status and filter_status != "all":
            items = [x for x in items if x.get("status") == filter_status]
        if filter_slug and filter_slug != "all":
            items = [x for x in items if x.get("lesson_slug") == filter_slug]

        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items

    @staticmethod
    def save_item(data: dict) -> dict:
        SAVED_VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
        items = VocabStore.get_all()
        
        word = data.get("word", "").strip()
        if not word:
            raise ValueError("Missing 'word' in vocabulary data")

        # Find existing word or ID
        item_id = data.get("id")
        existing_idx = -1
        for idx, it in enumerate(items):
            if item_id and it.get("id") == item_id:
                existing_idx = idx
                break
            elif it.get("word", "").lower() == word.lower():
                existing_idx = idx
                break

        now_ms = int(time.time() * 1000)
        
        # If translation is missing, auto lookup
        if not data.get("translation") or not data.get("ipa"):
            auto_info = lookup_word(word, context=data.get("context", ""))
            if not data.get("translation"):
                data["translation"] = auto_info.get("translation", "")
            if not data.get("ipa"):
                data["ipa"] = auto_info.get("ipa", "")
            if not data.get("pos"):
                data["pos"] = auto_info.get("pos", "")
            if not data.get("definition"):
                data["definition"] = auto_info.get("en_definition", "")

        saved_obj = {
            "id": item_id or f"vocab_{now_ms}_{len(items) + 1}",
            "word": word,
            "translation": data.get("translation", ""),
            "ipa": data.get("ipa", ""),
            "pos": data.get("pos", ""),
            "definition": data.get("definition", ""),
            "example": data.get("example", ""),
            "example_vi": data.get("example_vi", ""),
            "context": data.get("context", ""),
            "lesson_slug": data.get("lesson_slug", ""),
            "lesson_title": data.get("lesson_title", ""),
            "timestamp": data.get("timestamp", 0.0),
            "status": data.get("status", "need_review"),  # 'need_review' | 'learning' | 'mastered'
            "created_at": items[existing_idx].get("created_at", now_ms) if existing_idx >= 0 else now_ms,
            "updated_at": now_ms
        }

        if existing_idx >= 0:
            items[existing_idx] = saved_obj
        else:
            items.insert(0, saved_obj)

        with open(SAVED_VOCAB_FILE, "w", encoding="utf-8") as fp:
            json.dump(items, fp, ensure_ascii=False, indent=2)

        return saved_obj

    @staticmethod
    def update_status(target: str, status: str) -> bool:
        """
        Updates status of a word by id or word string.
        """
        items = VocabStore.get_all()
        found = False
        now_ms = int(time.time() * 1000)
        
        for it in items:
            if it.get("id") == target or it.get("word", "").lower() == target.lower():
                it["status"] = status
                it["updated_at"] = now_ms
                found = True
                break

        if found:
            with open(SAVED_VOCAB_FILE, "w", encoding="utf-8") as fp:
                json.dump(items, fp, ensure_ascii=False, indent=2)
        return found

    @staticmethod
    def delete_item(target: str) -> bool:
        """
        Deletes item by id or word.
        """
        items = VocabStore.get_all()
        init_len = len(items)
        items = [it for it in items if it.get("id") != target and it.get("word", "").lower() != target.lower()]
        
        if len(items) < init_len:
            with open(SAVED_VOCAB_FILE, "w", encoding="utf-8") as fp:
                json.dump(items, fp, ensure_ascii=False, indent=2)
            return True
        return False

    @staticmethod
    def export_csv() -> str:
        items = VocabStore.get_all()
        lines = ["Từ vựng,Phiên âm (IPA),Từ loại,Nghĩa tiếng Việt,Ngữ cảnh / Ví dụ,Bài học,Trạng thái"]
        for it in items:
            w = it.get("word", "").replace('"', '""')
            ipa = it.get("ipa", "").replace('"', '""')
            pos = it.get("pos", "").replace('"', '""')
            tr = it.get("translation", "").replace('"', '""')
            ctx = (it.get("context") or it.get("example") or "").replace('"', '""')
            les = it.get("lesson_title", "").replace('"', '""')
            st = it.get("status", "need_review")
            lines.append(f'"{w}","{ipa}","{pos}","{tr}","{ctx}","{les}","{st}"')
        return "\n".join(lines)


if __name__ == "__main__":
    test_word = sys.argv[1] if len(sys.argv) > 1 else "paradox"
    print(f"Testing lookup for: {test_word}")
    res = lookup_word(test_word)
    print(json.dumps(res, ensure_ascii=False, indent=2))
