"""Builders for raw model output used by the tests."""

from __future__ import annotations

HINDI_SCRIPT = (
    "दुनिया की सबसे गहरी जगह मारियाना ट्रेंच है। यहाँ पानी का दबाव इतना ज़्यादा है कि "
    "इंसान का शरीर टूट जाए। वैज्ञानिकों ने वहाँ ऐसे जीव खोजे जो पूरे अंधेरे में जीते हैं। "
    "ये जीव अपनी रोशनी बनाकर एक दूसरे से बात करते हैं। सोचिए, धरती पर ही एक अलग दुनिया है।"
)

LATIN_SCRIPT = (
    "This is a plain English script that is long enough to pass the length check but "
    "contains no Devanagari letters at all, which is exactly what we want to reject."
)


TITLES = [
    "समुद्र की सबसे गहरी जगह का रहस्य",
    "अंतरिक्ष में समय धीमा क्यों चलता है",
    "दिमाग हर रात सपने क्यों बनाता है",
    "मिस्र के पिरामिड का छिपा हुआ कमरा",
    "अंधेरे में शरीर क्यों डरता है",
    "धरती का सबसे पुराना जीव कौन है",
    "एआई हमारी नौकरी कैसे बदल रहा है",
    "जापान की ट्रेन हर मिनट सही क्यों है",
    "सपने में अपना चेहरा क्यों नहीं दिखता",
    "एक छोटी आदत जो ज़िंदगी बदल देती है",
    "मंगल ग्रह पर पानी कहाँ गया",
    "इंसान का दिल एक दिन में कितनी बार धड़कता है",
]


def raw_idea(index: int = 1, **overrides):
    """A complete, valid idea payload as the model should return it.

    Each ``index`` gets a genuinely different title. Appending a number to one
    title would not work: the duplicate check ignores one-character tokens, so
    those titles really are near-duplicates.
    """
    data = {
        "title": TITLES[(index - 1) % len(TITLES)],
        "hook": "धरती पर एक जगह है जहाँ सूरज की रोशनी कभी नहीं पहुँचती।",
        "script": HINDI_SCRIPT,
        "scenes": [
            {"scene": 1, "visual": "गहरे समुद्र का डार्क शॉट, बुलबुले ऊपर जाते हुए"},
            {"scene": 2, "visual": "पनडुब्बी की लाइट, अंधेरे में एक जीव चमकता है"},
            {"scene": 3, "visual": "ज़ूम इन: चमकते जीव और स्क्रीन पर टेक्स्ट"},
        ],
        "voiceover_text": HINDI_SCRIPT,
        "emotion": "mysterious",
        "music": "deep ocean drone",
        "subtitles": ["धरती पर एक गहरी दुनिया", "सूरज की रोशनी नहीं पहुँचती", "फिर भी जीवन है"],
        "description": "मारियाना ट्रेंच की अनसुनी बातें — छोटा वीडियो, बड़ा सवाल।",
        "hashtags": ["#mystery", "#ocean", "#facts"],
        "duration_sec": 45,
        "engagement_question": "क्या आप इतनी गहराई तक जाना चाहेंगे?",
        "category": "Mystery",
    }
    data.update(overrides)
    return data


def valid_idea(index: int = 1, **overrides):
    """The normalised idea produced from :func:`raw_idea`, or a clear failure."""
    from app.services.hackerai import normalise_idea

    idea, reason = normalise_idea(raw_idea(index, **overrides), ["Mystery"])
    assert idea is not None, f"test fixture is not valid: {reason}"
    return idea
