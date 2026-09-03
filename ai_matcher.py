"""Lightweight, explainable AI/ML-style matching engine for the hackathon MVP.

The MVP uses TF-IDF + cosine similarity and then adds transparent signals for
item type, color, category and shared words. It is intentionally lightweight so
it can run locally during a live demo.
"""

import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

COMMON_COLORS = {
    "black", "white", "blue", "red", "green", "yellow", "orange", "purple",
    "pink", "brown", "grey", "gray", "silver", "gold"
}

ITEM_ALIASES = {
    "headphone": {"headphone", "headphones", "earphone", "earphones", "earbuds"},
    "laptop": {"laptop", "notebook", "macbook"},
    "phone": {"phone", "smartphone", "mobile", "iphone", "android"},
    "wallet": {"wallet", "purse"},
    "bag": {"bag", "backpack", "rucksack"},
    "keys": {"key", "keys", "keychain"},
}

STOPWORDS = {
    "i", "me", "my", "mine", "the", "a", "an", "is", "it", "of", "to",
    "for", "and", "near", "at", "in", "on", "was", "were", "this", "that",
    "lost", "found", "did", "you", "have", "had", "with", "please"
}


def normalize(text):
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).strip()


def tokens(text):
    return {word for word in normalize(text).split() if word not in STOPWORDS and len(word) > 1}


def extract_color(text):
    words = set(normalize(text).split())
    return next((color for color in COMMON_COLORS if color in words), None)


def detect_item_family(text):
    words = set(normalize(text).split())
    for family, aliases in ITEM_ALIASES.items():
        if words & aliases:
            return family
    return None


def build_item_text(item):
    parts = [
        item["title"], item["description"], item["category"],
        item["color"], item["location"]
    ]
    return normalize(" ".join([p or "" for p in parts]))


def _score_query(query, item):
    """Return a strong, explainable score in the 0-99.9 range."""
    query_clean = normalize(query)
    item_text = build_item_text(item)

    # Semantic similarity is useful, but should not dominate obvious exact clues.
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    try:
        matrix = vectorizer.fit_transform([query_clean, item_text])
        semantic = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except ValueError:
        semantic = 0.0

    q_tokens = tokens(query_clean)
    i_tokens = tokens(item_text)
    overlap = len(q_tokens & i_tokens) / max(1, len(q_tokens))

    score = semantic * 35 + overlap * 35
    signals = []

    q_color = extract_color(query_clean)
    item_color = extract_color(item_text)
    if q_color and q_color == item_color:
        score += 12
        signals.append(f"{q_color} color")

    q_family = detect_item_family(query_clean)
    item_family = detect_item_family(item_text)
    if q_family and q_family == item_family:
        score += 13
        signals.append(q_family)

    q_category = normalize(item.get("category", ""))
    if q_category and q_category in query_clean:
        score += 5
        signals.append("category")

    if not signals:
        signals.append("semantic description")

    return min(99.9, score), signals


def match_lost_item(query, items):
    if not items:
        return []

    results = []
    for item in items:
        score, signals = _score_query(query, item)
        results.append({
            "item": item,
            "score": round(score, 1),
            "reason": "Matched using " + " + ".join(signals)
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:12]


def explain_match(query, item, score):
    _, signals = _score_query(query, item)
    return "Matched using " + " + ".join(signals)
