"""Turn refresh warnings that need a person into GitHub issues labelled ops-alert, and close them when they clear.

    python3 scripts/alerts.py [refresh-report.json]

Needs GITHUB_TOKEN (issues: write) and GITHUB_REPOSITORY. One issue per alert key; an alert only closes when the
step that raises it ran again and did not raise it. Never fails the workflow.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
STEP_OF = {"article-missing": "pageviews", "pageviews-drop": "pageviews", "source-changed": "sources",
           "source-gone": "sources", "link-broken": "sources"}
LABEL = "ops-alert"


def call(method, path, token, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                          "User-Agent": "response-ability-alerts", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def main(path):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo and os.path.exists(path)):
        print("alerts: nothing to do (no token, repo or report)")
        return 0
    with open(path) as fh:
        report = json.load(fh)
    ran = {step for step, ok in report.get("steps", {}).items() if ok}
    wanted = {a["key"]: a for a in report.get("alerts", [])}
    try:
        try:
            call("POST", "/repos/%s/labels" % repo, token, {"name": LABEL, "color": "d93f0b",
                                                             "description": "Raised by a scheduled job; needs a person"})
        except urllib.error.HTTPError:
            pass   # already exists
        issues = call("GET", "/repos/%s/issues?labels=%s&state=open&per_page=100" % (repo, LABEL), token)
        open_by_key = {}
        for issue in issues:
            body = issue.get("body") or ""
            if "<!-- alert:" in body:
                key = body.split("<!-- alert:", 1)[1].split(" -->", 1)[0]
                open_by_key[key] = issue
        for key, alert in wanted.items():
            if key in open_by_key:
                continue
            issue = call("POST", "/repos/%s/issues" % repo, token, {
                "title": alert["title"], "labels": [LABEL],
                "body": alert["body"] + "\n\n<!-- alert:%s -->\n_Opened by the scheduled refresh. It closes itself when "
                                        "the next run no longer sees the problem._" % key})
            print("opened #%s: %s" % (issue.get("number"), alert["title"]))
        for key, issue in open_by_key.items():
            step = STEP_OF.get(key.split(":", 1)[0])
            if key not in wanted and step in ran:
                call("POST", "/repos/%s/issues/%s/comments" % (repo, issue["number"]), token,
                     {"body": "The latest scheduled run no longer sees this problem. Closing."})
                call("PATCH", "/repos/%s/issues/%s" % (repo, issue["number"]), token,
                     {"state": "closed", "state_reason": "completed"})
                print("closed #%s" % issue["number"])
    except Exception as exc:
        print("::warning::alerts: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "refresh-report.json"))
