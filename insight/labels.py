"""Shared label definitions: the single source of truth for prompts, validation and docs.

Primary labels are the grading contract's common labels (GRADING_CONTRACT.md). The
subtopic layer is our own and only feeds issue grouping; `topic` is always the prefix.
"""

import re

TAXONOMY_VERSION = "taxonomy-v1"

TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("complaint", "request", "praise", "cancellation", "unclear")
# Contract precedence when several intents apply: first match wins.
INTENT_PRECEDENCE = ("cancellation", "complaint", "request", "praise", "unclear")
COMPLAINT_INTENTS = ("complaint", "cancellation")

TOPIC_DEFINITIONS = {
    "access": "Login, signup, password or account access",
    "usability": "Navigation, controls, layout, queue/playlist management, ad interruptions",
    "playback": "Playback failure, crashes, lag, connection failures, audio quality, resource use",
    "downloads": "Downloading, saved music, offline listening, disappearing downloads",
    "catalog": "Missing songs/artists, search/discovery, recommendations, lyrics availability",
    "billing": "Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls go here",
    "support": "Contacting support and the support response",
    "other": "General praise/criticism, unrelated content, or no supported specific topic",
}

# (issue_key, topic, subtopic, short name, definition, boundary note)
# issue_key is what the classifier chooses; issue_id (topic.subtopic) is the stable grouping key.
ISSUES = (
    ("access_login", "access", "login", "Login failures",
     "Cannot log in, keeps getting logged out, login or verification-code errors.",
     "A 'no internet connection' error while already logged in is playback_connection."),
    ("access_account", "access", "account", "Account and sign-up",
     "Sign-up or account creation, password reset, hacked, locked or deleted accounts, account settings.",
     "Choosing or paying for a plan is billing."),
    ("usability_ads", "usability", "ads", "Ad interruptions",
     "Too many, too long, too loud or repeated ads; ads interrupting listening.",
     "Complaints that features need Premium are billing_premium_only, even when ads are also mentioned."),
    ("usability_navigation", "usability", "navigation", "Navigation and layout",
     "Hard to find things, confusing layout, redesigns or home-screen changes, buttons moved or removed.",
     "A missing control described as Premium-only is billing_premium_only."),
    ("usability_library", "usability", "library", "Library, queue and playlists",
     "Managing the queue, playlists, liked songs or library; shuffle or repeat controls that misbehave.",
     "Forced shuffle or skip limits for free users are billing_premium_only."),
    ("usability_other", "usability", "other", "Other control annoyances",
     "Notifications, emails, settings, toggles, widgets and other interaction annoyances.",
     "Use only when no other usability option fits."),
    ("playback_stops", "playback", "stops", "Playback stops or skips",
     "Music stops, pauses, skips by itself, will not start, or plays the wrong song.",
     "Skip limits for free users are billing_premium_only."),
    ("playback_crash", "playback", "crash", "Crashes and freezes",
     "App crashes, freezes, will not open or load, blank screens.",
     ""),
    ("playback_connection", "playback", "connection", "Connection errors",
     "App says there is no internet or that it is offline while connected; network or streaming errors.",
     ""),
    ("playback_devices", "playback", "devices", "Devices and casting",
     "Bluetooth, casting, Spotify Connect, cars, smartwatches, smart speakers, TVs, consoles, other integrations.",
     ""),
    ("playback_performance", "playback", "performance", "Performance and audio quality",
     "Lag, slowness, battery or storage use, audio quality or volume problems.",
     ""),
    ("downloads_offline", "downloads", "offline", "Downloads and offline listening",
     "Downloading, saved music, offline mode, downloads that disappear or fail.",
     "Offline listening described only as a Premium paywall is billing_premium_only."),
    ("catalog_missing", "catalog", "missing", "Missing or removed content",
     "Songs, artists, albums or podcasts missing, removed, greyed out or unavailable.",
     ""),
    ("catalog_search", "catalog", "search", "Search and discovery",
     "Search results, finding songs or artists, browsing and discovery.",
     ""),
    ("catalog_recommendations", "catalog", "recommendations", "Recommendations",
     "Recommendations, the algorithm, autoplay or radio picks, the DJ, unwanted suggested songs.",
     ""),
    ("catalog_lyrics", "catalog", "lyrics", "Lyrics availability",
     "Lyrics missing, wrong or not loading.",
     "Lyrics locked behind Premium is billing_premium_only."),
    ("catalog_podcasts", "catalog", "podcasts", "Podcasts and audiobooks",
     "Podcast, audiobook or video-podcast content and episodes.",
     ""),
    ("billing_premium_only", "billing", "premium_only", "Premium-only restrictions",
     "Features locked to Premium: skip limits, forced shuffle, cannot pick songs, cannot repeat or rewind, "
     "lyrics or offline behind a paywall, 'everything needs Premium now'.",
     "Merely mentioning Premium is not enough; the complaint must be about the paywall or entitlement."),
    ("billing_price", "billing", "price", "Price and value",
     "Premium price, price increases, value for money.",
     ""),
    ("billing_payment", "billing", "payment", "Charges and subscriptions",
     "Unexpected or repeated charges, refunds, payment failures, a subscription or trial not activating, "
     "cancellation or plan problems.",
     "Music crashing for a paying customer is playback, not billing."),
    ("support_contact", "support", "contact", "Customer support",
     "Contacting customer support, support response quality or absence of a response.",
     ""),
    ("other_general", "other", "general", "General or unrelated",
     "General praise or criticism with no specific feature, unrelated content (politics, artists, boycotts), "
     "or meaningless text.",
     "Use when no specific product area is supported by the text."),
)

ISSUE_KEYS = tuple(i[0] for i in ISSUES)
ISSUE_BY_KEY = {i[0]: {"key": i[0], "topic": i[1], "subtopic": i[2], "issue_id": f"{i[1]}.{i[2]}",
                       "name": i[3], "definition": i[4], "boundary": i[5]} for i in ISSUES}
ISSUE_BY_ID = {v["issue_id"]: v for v in ISSUE_BY_KEY.values()}
SUBTOPICS = {t: tuple(v["subtopic"] for v in ISSUE_BY_KEY.values() if v["topic"] == t) for t in TOPICS}

# Business areas named in the assignment's decision question. Derived, not a grading label.
AREA_OF_TOPIC = {
    "access": "access/onboarding",
    "usability": "usability",
    "playback": "playback/performance",
    "downloads": "playback/performance",
    "billing": "billing/support",
    "support": "billing/support",
    "catalog": "catalog/content",
    "other": "general/unspecified",
}
DECISION_AREAS = ("access/onboarding", "usability", "playback/performance", "billing/support")

SEVERITY = {
    1: "No reported problem: praise, neutral/unclear content, or a pure feature request",
    2: "Dislike, generic criticism, minor annoyance, or a cosmetic issue; no supported functional loss",
    3: "A degraded or restricted function; some use or workaround remains",
    4: "A clearly blocked core task, such as inability to log in or play music",
    5: "Explicit serious financial, privacy, or data harm; an expensive plan, a crash, or angry language alone is insufficient",
}
SEVERITY_KEYS = {"no_problem": 1, "annoyance": 2, "degraded": 3, "blocked": 4, "serious_harm": 5}

# Sentiment: -1 (very negative) .. +1 (very positive), five anchored levels.
SENTIMENT_LEVELS = (
    (-1.0, "Very negative: angry, hostile or strongly dissatisfied"),
    (-0.5, "Somewhat negative: dissatisfied, disappointed or critical"),
    (0.0, "Neutral or balanced: no clear feeling, or praise and criticism in equal measure"),
    (0.5, "Somewhat positive: satisfied or mildly pleased"),
    (1.0, "Very positive: enthusiastic praise"),
)
SENTIMENT_TOLERANCE = 0.5  # predeclared: two sentiments within one level count as agreeing

# Severity must match intent where the contract's definitions imply it (enforced in code,
# never trusted to the classifier): praise/request/unclear report no problem, so severity 1;
# a complaint reports a negative experience, so at least severity 2.
def consistency_problems(intent: str, severity: int) -> list:
    problems = []
    if intent in ("praise", "request", "unclear") and severity != 1:
        problems.append(f"{intent} with severity {severity} (definition implies 1)")
    if intent == "complaint" and severity < 2:
        problems.append("complaint with severity 1 (definition implies at least 2)")
    return problems


def reconcile(intent: str, severity: int) -> int:
    """Deterministic, documented repair used only when no fallback resolved the conflict."""
    if intent in ("praise", "request", "unclear"):
        return 1
    if intent == "complaint" and severity < 2:
        return 2
    return severity


# Entities: explicitly mentioned product terms, matched by code (case-insensitive, word bounded).
# The output is the canonical term; a term is listed only if the review text contains it.
ENTITY_PATTERNS = (
    ("ads", r"\bads?\b|\badverts?\b|\badvertisements?\b|\bcommercials?\b"),
    ("premium", r"\bpremium\b"),
    ("subscription", r"\bsubscri(?:ption|ptions|be|bed|bing)\b"),
    ("free tier", r"\bfree (?:version|tier|plan|users?|account)\b"),
    ("price", r"\bprices?\b|\bpricing\b|\bexpensive\b"),
    ("refund", r"\brefunds?\b"),
    ("payment", r"\bpayments?\b|\bcharged\b|\bbilling\b"),
    ("skips", r"\bskips?\b|\bskipping\b|\bskipped\b"),
    ("shuffle", r"\bshuffl(?:e|ed|es|ing)\b"),
    ("repeat", r"\brepeat\b"),
    ("queue", r"\bqueue\b"),
    ("playlist", r"\bplay ?lists?\b"),
    ("liked songs", r"\bliked songs\b"),
    ("library", r"\blibrary\b"),
    ("lyrics", r"\blyrics?\b"),
    ("podcasts", r"\bpodcasts?\b"),
    ("audiobooks", r"\baudio ?books?\b"),
    ("downloads", r"\bdownload(?:s|ed|ing)?\b"),
    ("offline", r"\boffline\b"),
    ("search", r"\bsearch(?:es|ing|ed)?\b"),
    ("recommendations", r"\brecommendations?\b|\balgorithm\b"),
    ("dj", r"\bdj\b"),
    ("discover weekly", r"\bdiscover weekly\b"),
    ("release radar", r"\brelease radar\b"),
    ("daily mix", r"\bdaily mix(?:es)?\b"),
    ("wrapped", r"\bwrapped\b"),
    ("login", r"\blog ?in\b|\bsign ?in\b|\blogged out\b|\blog out\b"),
    ("password", r"\bpasswords?\b"),
    ("account", r"\baccounts?\b"),
    ("sign up", r"\bsign ?up\b|\bregistration\b"),
    ("update", r"\bupdates?\b|\bupdated\b"),
    ("crash", r"\bcrash(?:es|ed|ing)?\b"),
    ("bluetooth", r"\bbluetooth\b"),
    ("casting", r"\bchromecast\b|\bcasting\b|\bcast to\b"),
    ("spotify connect", r"\bspotify connect\b"),
    ("android auto", r"\bandroid auto\b"),
    ("car", r"\bcar\b"),
    ("smartwatch", r"\bwear ?os\b|\bsmart ?watch\b"),
    ("smart speaker", r"\balexa\b|\bgoogle home\b|\bsmart speakers?\b"),
    ("tv", r"\bsmart tv\b|\btv\b"),
    ("game console", r"\bxbox\b|\bplaystation\b|\bps[45]\b"),
    ("widget", r"\bwidgets?\b"),
    ("notifications", r"\bnotifications?\b"),
    ("battery", r"\bbattery\b"),
    ("storage", r"\bstorage\b|\bsd card\b"),
    ("audio quality", r"\baudio quality\b|\bsound quality\b|\bhi-?fi\b|\bhi-?res\b|\blossless\b"),
    ("volume", r"\bvolume\b"),
    ("equalizer", r"\bequali[sz]er\b"),
    ("home screen", r"\bhome ?(?:screen|page)\b"),
    ("customer support", r"\bcustomer (?:support|service|care)\b|\bsupport team\b"),
    ("family plan", r"\bfamily plan\b|\bduo plan\b|\bstudent (?:plan|discount|premium)\b"),
    ("free trial", r"\bfree trial\b|\btrial\b"),
    ("interface", r"\binterface\b|\bui\b|\blayout\b"),
    ("sleep timer", r"\bsleep timer\b"),
    ("gapless playback", r"\bcrossfade\b|\bgapless\b"),
    ("video", r"\bvideos?\b"),
)
_ENTITY_RES = tuple((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in ENTITY_PATTERNS)
ENTITY_LEXICON_VERSION = "entities-v1"


def extract_entities(text: str) -> list:
    """Canonical feature terms explicitly present in the text, in order of first mention."""
    hits = []
    for name, regex in _ENTITY_RES:
        m = regex.search(text)
        if m:
            hits.append((m.start(), name))
    seen, out = set(), []
    for _, name in sorted(hits):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def letters_profile(text: str) -> dict:
    """Code-side language/legibility signals used for needs_review (no model involved)."""
    letters = [ch for ch in text if ch.isalpha()]
    non_latin = sum(1 for ch in letters if ord(ch) > 0x24F)
    return {
        "letters": len(letters),
        "non_latin_fraction": round(non_latin / len(letters), 3) if letters else None,
    }


def code_review_flags(text: str) -> list:
    """Reasons code alone marks a record needs_review (emoji-only text, non-Latin script)."""
    prof = letters_profile(text)
    flags = []
    if prof["letters"] == 0:
        flags.append("no_letters")
    elif prof["non_latin_fraction"] is not None and prof["non_latin_fraction"] > 0.5:
        flags.append("mostly_non_latin_script")
    return flags
