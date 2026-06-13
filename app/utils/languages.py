"""
Language code/name resolution for Sunflower translation.

Maps SALT ISO 639-3 codes to full language names and validates that a
requested language is supported by the Sunflower model. The Sunflower
instruction format requires full language names, so API clients may send
either an ISO code (e.g. ``lug``) or a full name (e.g. ``Luganda``),
case-insensitively.
"""

from typing import Dict, NamedTuple

# Full SALT language map (code -> canonical full name). Includes languages
# beyond what Sunflower supports; only names in SUNFLOWER_LANGUAGES are
# accepted by resolve_language().
SALT_LANGUAGE_NAMES: Dict[str, str] = {
    "ach": "Acholi",
    "eng": "English",
    "ibo": "Igbo",
    "lgg": "Lugbara",
    "lug": "Luganda",
    "nyn": "Runyankole",
    "swa": "Swahili",
    "teo": "Ateso",
    "xog": "Lusoga",
    "ttj": "Rutooro",
    "kin": "Kinyarwanda",
    "myx": "Lumasaba",
    "adh": "Jopadhola",
    "alz": "Alur",
    "bfa": "Bari",
    "cgg": "Rukiga",
    "gwr": "Lugwere",
    "ikx": "Ik",
    "kdi": "Kumam",
    "kdj": "Karamojong",
    "keo": "Kakwa",
    "koo": "Rukonjo",
    "kpz": "Kupsabiny",
    "laj": "Lango",
    "led": "Lendu",
    "lsm": "Samia",
    "lth": "Thur",
    "luc": "Aringa",
    "luo": "Luo",
    "lzm": "Lulubo",
    "mhi": "Ma'di",
    "ndp": "Kebu",  # replacing Ndo with Kebu
    "pok": "Pokot",
    "rub": "Lugungu",
    "ruc": "Ruruuli",
    "rwm": "Kwamba",
    "sbx": "Sebei",
    "soc": "So",
    "tlj": "Lubwisi",  # Bwisi-Talinga
    "nuj": "Lunyole",
    "nyo": "Runyoro",
    # Rest of Africa
    "afr": "Afrikaans",
    "aka": "Akan",
    "amh": "Amharic",
    "bam": "Bambara",
    "bem": "Bemba",
    "ber": "Berber",
    "nya": "Chichewa",
    "dga": "Dagaare",
    "dag": "Dagbani",
    "din": "Dinka",
    "ewe": "Ewe",
    "fra": "French",
    "ful": "Fulani",
    "kik": "Kikuyu",
    "hau": "Hausa",
    "kpo": "Ikposo",
    "kab": "Kabyle",
    "kln": "Kalenjin",
    "kau": "Kanuri",
    "run": "Kirundi",
    "lin": "Lingala",
    "luy": "Luhya",
    "mlg": "Malagasy",
    "nbl": "Ndebele",
    "pcm": "Nigerian Pidgin",
    "orm": "Oromo",
    "sot": "Sotho",
    "sna": "Shona",
    "som": "Somali",
    "tsn": "Tswana",
    "wol": "Wolof",
    "xho": "Xhosa",
    "yor": "Yoruba",
    "zul": "Zulu",
}

# The 32 languages the Sunflower model supports for translation.
SUNFLOWER_LANGUAGES = (
    "Acholi",
    "Alur",
    "Aringa",
    "Ateso",
    "Bari",
    "English",
    "Jopadhola",
    "Kakwa",
    "Karamojong",
    "Kinyarwanda",
    "Kumam",
    "Kupsabiny",
    "Kwamba",
    "Lango",
    "Lubwisi",
    "Luganda",
    "Lugbara",
    "Lugungu",
    "Lugwere",
    "Lumasaba",
    "Lunyole",
    "Lusoga",
    "Ma'di",
    "Pokot",
    "Rukiga",
    "Rukonjo",
    "Runyankole",
    "Runyoro",
    "Ruruuli",
    "Rutooro",
    "Samia",
    "Swahili",
)

# Input spelling variants -> canonical SALT name.
LANGUAGE_ALIASES: Dict[str, str] = {
    "runyankore": "Runyankole",
    "dhopadhola": "Jopadhola",
}


class UnsupportedLanguageError(ValueError):
    """Raised when a language is not supported by Sunflower translation."""


class ResolvedLanguage(NamedTuple):
    """A validated language: canonical ISO code and full name."""

    code: str
    name: str


_SUNFLOWER_NAME_SET = set(SUNFLOWER_LANGUAGES)
_CODE_TO_NAME: Dict[str, str] = {
    code: name
    for code, name in SALT_LANGUAGE_NAMES.items()
    if name in _SUNFLOWER_NAME_SET
}
_NAME_TO_CODE: Dict[str, str] = {
    name.lower(): code for code, name in _CODE_TO_NAME.items()
}


def resolve_language(value: str) -> ResolvedLanguage:
    """Resolve an ISO code or full language name to a ResolvedLanguage.

    Accepts ISO 639-3 codes ("lug"), full names ("Luganda"), and known
    spelling variants ("Runyankore"), case-insensitively and ignoring
    surrounding whitespace.

    Raises:
        UnsupportedLanguageError: If the value does not resolve to one of
            the 32 Sunflower-supported languages.
    """
    cleaned = (value or "").strip()
    key = cleaned.lower()

    if key in _CODE_TO_NAME:
        return ResolvedLanguage(code=key, name=_CODE_TO_NAME[key])

    name = LANGUAGE_ALIASES.get(key)
    if name is None and key in _NAME_TO_CODE:
        name = _CODE_TO_NAME[_NAME_TO_CODE[key]]

    if name is not None:
        return ResolvedLanguage(code=_NAME_TO_CODE[name.lower()], name=name)

    raise UnsupportedLanguageError(
        f"Unsupported language: '{cleaned}'. "
        f"Supported languages: {', '.join(sorted(SUNFLOWER_LANGUAGES))} "
        f"(full name or ISO code)."
    )
