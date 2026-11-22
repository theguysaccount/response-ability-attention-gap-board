"""Submit the site's URLs to IndexNow (Bing, Yandex, Seznam, Naver and others share submissions).

    python3 scripts/indexnow.py build/urls.txt [base_url]

Skipped when SITE_INDEXABLE is false. The key file is published at <base>/<key>.txt by the build.
Failures are reported but never fail a deploy.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "https://theguysaccount.github.io/response-ability-attention-gap-board"


def main(url_file, base):
    if (os.environ.get("SITE_INDEXABLE") or "true").strip().lower() in ("false", "0", "no"):
        print("IndexNow: skipped (SITE_INDEXABLE is false)")
        return 0
    base = base.rstrip("/")
    with open(os.path.join(ROOT, "site", "indexnow-key.txt")) as fh:
        key = fh.read().strip()
    with open(url_file) as fh:
        urls = [u.strip() for u in fh if u.strip().startswith(base + "/")]
    if not urls:
        print("IndexNow: no URLs to submit")
        return 0
    body = {"host": urllib.parse.urlparse(base).netloc, "key": key, "keyLocation": "%s/%s.txt" % (base, key),
            "urlList": urls[:10000]}
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "response-ability-attention-gap-board/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print("IndexNow: HTTP %s for %d URLs" % (resp.status, len(body["urlList"])))
    except urllib.error.HTTPError as exc:
        print("IndexNow: HTTP %s (%s)" % (exc.code, exc.read()[:200]))
    except Exception as exc:
        print("IndexNow: failed (%s)" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.environ.get("SITE_URL") or DEFAULT_BASE))
