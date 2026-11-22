"""Small polite HTTP client shared by the refresh and health scripts."""
import json
import time
import urllib.error
import urllib.request

REPO_URL = "https://github.com/theguysaccount/response-ability-attention-gap-board"
# Wikimedia asks automated clients to identify themselves with a contact; the repository is the contact.
UA = "response-ability-attention-gap-board/1.0 (+%s)" % REPO_URL
BOT_WALLS = (401, 403, 405, 429)   # the server answered but refuses scripts: not evidence that a page is gone


class Fetch(object):
    """Result of one request: status 0 means no HTTP answer at all (DNS, TLS, timeout)."""

    def __init__(self, status, body=b"", url="", error=""):
        self.status, self.body, self.url, self.error = status, body, url, error

    @property
    def ok(self):
        return 200 <= self.status < 300

    def text(self):
        return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def fetch(url, timeout=40, tries=3, pause=2.0, accept="*/*", limit=4000000):
    """GET with retries on network errors, 429 and 5xx. Never raises."""
    last = Fetch(0, url=url, error="not tried")
    for attempt in range(tries):
        if attempt:
            time.sleep(pause * attempt)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return Fetch(resp.status, resp.read(limit), resp.geturl())
        except urllib.error.HTTPError as exc:
            last = Fetch(exc.code, url=url, error="HTTP %s" % exc.code)
            if exc.code not in (429, 500, 502, 503, 504):
                return last
        except Exception as exc:  # URLError, timeout, reset, bad TLS
            last = Fetch(0, url=url, error="%s: %s" % (type(exc).__name__, exc))
    return last
