"""
Vision + matching.

Two jobs:

1. describe_image() runs once per upload. The vision model turns the photo
   into structured text (title, category, color, brand, tags, description)
   which gets stored in the DB. This is the expensive call, and it happens
   once per item -- never per search.

2. rank_matches() takes someone's "I lost a blue water bottle" query plus a
   shortlist of stored items and asks the model which ones actually match,
   with a score and a one-line reason.

Both degrade gracefully: with no API key the app still works, it just falls
back to keyword scoring over whatever text is in the DB.
"""

import base64
import json
import os
import re
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = 45


def available():
    return bool(API_KEY)


class AIError(RuntimeError):
    pass


def _call(parts, temperature=0.2):
    """POST to Gemini generateContent and return the parsed JSON body."""
    if not API_KEY:
        raise AIError("GEMINI_API_KEY is not set")

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": temperature,
        },
    }
    headers = {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}
    url = f"{ENDPOINT}/models/{MODEL}:generateContent"

    resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    if resp.status_code == 503:
        # Overload is usually a brief spike; one retry beats failing the upload.
        time.sleep(2)
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)

    if resp.status_code == 404:
        # The body usually names the replacement model when one is retired.
        raise AIError(f"{_api_message(resp) or f'Model {MODEL!r} not found.'} "
                      f"Set GEMINI_MODEL, or run `python3 scripts/check_ai.py`.")
    if resp.status_code == 429:
        raise AIError("Gemini free-tier rate limit hit. Wait a minute and try again.")
    if resp.status_code == 503:
        raise AIError(f"'{MODEL}' is overloaded right now. Try again in a moment.")
    if resp.status_code != 200:
        raise AIError(f"Gemini returned HTTP {resp.status_code}: {_api_message(resp) or resp.text[:200]}")

    body = resp.json()
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise AIError(f"Unexpected response shape: {json.dumps(body)[:300]}")
    return _parse_json(text)


def _api_message(resp):
    """Pull Google's human-readable error string out of a failed response."""
    try:
        return resp.json().get("error", {}).get("message", "").strip()
    except ValueError:
        return ""


def _parse_json(text):
    """Models occasionally wrap JSON in ``` fences despite being told not to."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        match = re.search(r"[\[{].*[\]}]", text, re.S)
        if not match:
            raise AIError(f"Model did not return JSON: {text[:200]}")
        return json.loads(match.group(0))


def list_models():
    """Used by scripts/check_ai.py."""
    resp = requests.get(
        f"{ENDPOINT}/models",
        headers={"x-goog-api-key": API_KEY},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("models", [])


# --------------------------------------------------------------------------
# 1. Describe an uploaded photo
# --------------------------------------------------------------------------

DESCRIBE_PROMPT = """You are cataloguing an item for a high school campus lost and found.
Look at the photo and describe ONLY the lost item itself -- ignore the table,
floor, hand, or background it is sitting on.

Return JSON with exactly these keys:
{
  "title": "short name, 2-5 words, e.g. 'Blue Hydro Flask' or 'Black wired earbuds'",
  "category": "one of: bottle, electronics, clothing, bag, book, stationery, jewelry, eyewear, keys, id_card, sports, charger, headphones, umbrella, other",
  "color": "main color(s), lowercase, comma separated",
  "brand": "visible brand name, or null if none is legible",
  "description": "2-3 sentences someone could match against from memory: shape, material, condition, stickers, text, wear, straps, logos",
  "tags": ["8-15 lowercase single-word or two-word search keywords, including synonyms someone might type: e.g. 'water bottle', 'flask', 'thermos', 'blue', 'dented', 'sticker'"],
  "distinguishing_marks": "anything unique -- scratches, stickers, engraving, keychains, a name written on it -- or null"
}

Be specific about color and brand; those are what people search by.
If the photo does not clearly show an object, set title to "Unclear photo".
Output raw JSON only."""


def describe_image(image_bytes, mime_type="image/jpeg"):
    """Photo -> structured description dict. Raises AIError on failure."""
    data = base64.b64encode(image_bytes).decode("ascii")
    result = _call(
        [
            {"text": DESCRIBE_PROMPT},
            {"inline_data": {"mime_type": mime_type, "data": data}},
        ]
    )
    if not isinstance(result, dict):
        raise AIError("Expected a JSON object from the vision model")

    tags = result.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]

    return {
        "title": (result.get("title") or "Found item").strip()[:120],
        "category": _clean(result.get("category")),
        "color": _clean(result.get("color")),
        "brand": _clean(result.get("brand")),
        "description": _clean(result.get("description")) or "",
        "tags": [str(t).strip().lower() for t in tags if str(t).strip()][:20],
        "distinguishing_marks": _clean(result.get("distinguishing_marks")),
    }


def _clean(value):
    """Models like to say the string "null" or "none"."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "unknown", "not visible"}:
        return None
    return text


# --------------------------------------------------------------------------
# 2. Match a search query against stored items
# --------------------------------------------------------------------------

RANK_PROMPT = """A student lost something at school and described it from memory.
Below is the catalogue of items currently in the lost and found.

Their description:
\"\"\"{query}\"\"\"

Catalogue:
{catalogue}

Decide which catalogue items could plausibly be the thing they lost.

Rules:
- Memory is imprecise. "navy" may be logged as "dark blue"; "water bottle" may
  be a "thermos"; they may misremember the brand. Reward matches on the object
  type and standout details over exact wording.
- A wrong object type is a hard no, however well the color matches.
- Do not invent items. Only use the ids listed above.
- Omit anything below a score of 25.

Return a JSON array, best match first:
[{{"id": <catalogue id>, "score": <0-100 confidence>, "reason": "<one short sentence, addressed to the student, on why this might be theirs>"}}]

Return [] if nothing plausibly matches. Output raw JSON only."""


def rank_matches(query, items, max_items=40):
    """
    Ask the model which items match the query.
    Returns {item_id: {"score": int, "reason": str}} or raises AIError.
    """
    shortlist = items[:max_items]
    if not shortlist:
        return {}

    lines = []
    for it in shortlist:
        bits = [f"id {it['id']}: {it['title']}"]
        for label, key in (("category", "category"), ("color", "color"), ("brand", "brand")):
            if it.get(key):
                bits.append(f"{label}: {it[key]}")
        if it.get("ai_description"):
            bits.append(f"details: {it['ai_description']}")
        if it.get("user_note"):
            bits.append(f"finder's note: {it['user_note']}")
        if it.get("tags"):
            bits.append("tags: " + ", ".join(it["tags"]))
        if it.get("found_location"):
            bits.append(f"found at: {it['found_location']}")
        lines.append(" | ".join(bits))

    result = _call(
        [{"text": RANK_PROMPT.format(query=query.strip(), catalogue="\n".join(lines))}],
        temperature=0.1,
    )

    if isinstance(result, dict):
        # Some responses come back as {"matches": [...]}.
        result = next((v for v in result.values() if isinstance(v, list)), [])

    valid_ids = {it["id"] for it in shortlist}
    ranked = {}
    for entry in result or []:
        if not isinstance(entry, dict):
            continue
        try:
            item_id = int(entry.get("id"))
            score = int(float(entry.get("score", 0)))
        except (TypeError, ValueError):
            continue
        if item_id in valid_ids and score >= 25:
            ranked[item_id] = {
                "score": max(0, min(100, score)),
                "reason": _clean(entry.get("reason")) or "",
            }
    return ranked


# --------------------------------------------------------------------------
# Keyword fallback -- also used to shortlist before calling the model
# --------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "and", "are", "around", "at", "be", "black", "but", "can", "cant",
    "day", "did", "do", "for", "from", "had", "has", "have", "i", "if", "in", "is",
    "it", "its", "ive", "last", "lost", "me", "missing", "my", "of", "on", "or",
    "somewhere", "that", "the", "there", "this", "to", "today", "was", "week",
    "with", "yesterday", "you",
}
STOPWORDS.discard("black")  # colors matter here, unlike in most search boxes

SYNONYMS = {
    "bottle": {"flask", "thermos", "hydroflask", "canteen", "tumbler", "nalgene"},
    "flask": {"bottle", "thermos", "hydroflask"},
    "laptop": {"macbook", "chromebook", "notebook", "computer"},
    "charger": {"cable", "cord", "adapter", "brick", "plug", "usb"},
    "earbuds": {"airpods", "headphones", "earphones", "buds"},
    "headphones": {"earbuds", "airpods", "headset"},
    "phone": {"iphone", "android", "cellphone", "smartphone"},
    "glasses": {"eyeglasses", "spectacles", "sunglasses", "eyewear"},
    "jacket": {"coat", "hoodie", "sweatshirt", "windbreaker", "pullover"},
    "hoodie": {"sweatshirt", "jacket", "sweater"},
    "backpack": {"bag", "rucksack", "knapsack", "jansport"},
    "bag": {"backpack", "tote", "purse", "pouch"},
    "id": {"idcard", "badge", "card", "onecard"},
    "keys": {"key", "keychain", "fob", "lanyard"},
    "calculator": {"ti84", "ti-84", "casio", "graphing"},
    "notebook": {"binder", "journal", "notepad"},
    "ring": {"band", "jewelry"},
    "watch": {"smartwatch", "fitbit", "applewatch"},
    "umbrella": {"parasol"},
    "navy": {"blue", "dark"},
    "maroon": {"red", "burgundy"},
    "grey": {"gray", "silver"},
    "gray": {"grey", "silver"},
    "teal": {"turquoise", "cyan", "aqua"},
    "purple": {"violet", "lavender"},
}


def _tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 1 and w not in STOPWORDS}


def _expand(tokens):
    out = set(tokens)
    for token in tokens:
        out |= SYNONYMS.get(token, set())
    return out


def keyword_score(query, item):
    """Cheap lexical relevance, 0-100. Used to shortlist and as the no-key fallback."""
    q = _expand(_tokens(query))
    if not q:
        return 0

    strong = _expand(_tokens(" ".join(filter(None, [
        item.get("title"), item.get("category"), item.get("color"),
        item.get("brand"), " ".join(item.get("tags") or []),
    ]))))
    weak = _tokens(" ".join(filter(None, [
        item.get("ai_description"), item.get("user_note"), item.get("found_location"),
    ])))

    hits = 0.0
    for token in q:
        if token in strong:
            hits += 1.0
        elif token in weak:
            hits += 0.5
        elif any(token in w or w in token for w in strong if len(w) > 3 and len(token) > 3):
            hits += 0.4  # partial: "hydroflask" vs "hydro"

    return int(min(100, round(100 * hits / len(q))))
