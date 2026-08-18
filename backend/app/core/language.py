_LANGUAGE_NAMES = {"ar": "العربية", "en": "English"}


def language_display_name(language_code: str) -> str:
    return _LANGUAGE_NAMES.get(language_code, language_code)
