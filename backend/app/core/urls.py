def normalize_hostname(hostname: str) -> str:
    return hostname.lower().removeprefix("www.")
