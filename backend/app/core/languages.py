"""Languages the app is offered in.

One registry, used by the API, the translation cache and (mirrored) by the
client. Adding a language is adding a row here — nothing else in the system
needs to know the list.

English is the SOURCE language, not merely one of the options: the agents
write their analysis in English and everything else is a translation of it.
That is deliberate. The models reason about finance most reliably in
English, the terminology is native to it, and translating out of English is
cleaner than translating into it.

Choosing a language here is a product decision, not a legal one. Shipping
the app in German does not make it lawful to offer investment analysis in
Germany — distribution has to be restricted per country in App Store Connect
and the Play Console, separately and deliberately.
"""
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Language:
    code: str
    #: Name in the language itself — what a speaker recognises in a picker.
    native_name: str
    english_name: str
    rtl: bool = False


#: Ordered: English first as the source, then by expected audience size.
LANGUAGES: List[Language] = [
    Language("en", "English", "English"),
    Language("he", "עברית", "Hebrew", rtl=True),
    Language("de", "Deutsch", "German"),
    Language("es", "Español", "Spanish"),
    Language("pt-BR", "Português (Brasil)", "Portuguese (Brazil)"),
    Language("fr", "Français", "French"),
    # The app is already built for right-to-left because of Hebrew, so Arabic
    # costs almost nothing structurally — for most apps it is a large rewrite.
    Language("ar", "العربية", "Arabic", rtl=True),
    Language("it", "Italiano", "Italian"),
    Language("ko", "한국어", "Korean"),
    Language("ja", "日本語", "Japanese"),
]

BY_CODE: Dict[str, Language] = {lang.code: lang for lang in LANGUAGES}

SOURCE_LANGUAGE = "en"
DEFAULT_LANGUAGE = "en"

RTL_CODES = {lang.code for lang in LANGUAGES if lang.rtl}


def is_supported(code: str | None) -> bool:
    return bool(code) and code in BY_CODE


def normalize(code: str | None) -> str:
    """Best supported match for a device or profile language tag.

    Devices report tags like "he-IL", "pt-BR", "en-US". An exact match wins;
    otherwise the base subtag is tried, so "de-AT" lands on German rather
    than silently falling back to English. Anything unknown becomes the
    default — never an error, because a language we do not have is a normal
    thing for a store app to meet.
    """
    if not code:
        return DEFAULT_LANGUAGE
    tag = code.strip()
    if tag in BY_CODE:
        return tag
    # Case-insensitive exact match ("PT-br").
    for known in BY_CODE:
        if known.lower() == tag.lower():
            return known
    base = tag.split("-")[0].split("_")[0].lower()
    if base in BY_CODE:
        return base
    # A regional variant of a language we carry only regionally: pt-PT → pt-BR
    # is a better answer than English for a Portuguese speaker.
    for known in BY_CODE:
        if known.split("-")[0].lower() == base:
            return known
    return DEFAULT_LANGUAGE
