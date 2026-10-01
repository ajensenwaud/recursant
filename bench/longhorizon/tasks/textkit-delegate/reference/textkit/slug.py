import unicodedata
import re


def slugify(text, max_len=50):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if len(s) > max_len:
        cut = s[:max_len]
        if s[max_len] != "-" and "-" in cut:
            cut = cut[:cut.rindex("-")]
        s = cut.strip("-")
    return s or "n-a"
