"""Turn an HTML page into comparable plain text, and find a quoted phrase in it."""
import html
import re
import unicodedata

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
_DATE = re.compile(r"\b(\d{1,2}) (%s) (20\d\d)\b" % "|".join(MONTHS))


def page_text(markup):
    """Visible text of an HTML document with every run of whitespace collapsed to one space."""
    s = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", markup)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return squash(html.unescape(s))


def squash(text):
    """Normalise for comparison: compatibility forms, straight quotes, single spaces, lower case."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-").replace("‑", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


def has_quote(text, quote):
    """True when the quote appears in already-squashed page text."""
    return squash(quote) in text


def page_date(markup, before="key facts"):
    """The publication date a WHO fact sheet prints under its title (ISO), or '' when none is found.

    The date is the last "D Month YYYY" before the first "Key facts" heading. Pages without that
    heading fall back to the first date in the document.
    """
    s = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", markup)
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", s)))
    cut = plain.lower().find(before)
    found = _DATE.findall(plain[:cut]) if cut > 0 else []
    if found:
        day, month, year = found[-1]
    else:
        m = _DATE.search(plain)
        if not m:
            return ""
        day, month, year = m.groups()
    return "%s-%02d-%02d" % (year, MONTHS.index(month) + 1, int(day))
