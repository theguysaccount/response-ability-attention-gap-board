"""site/assets/core.js and board/data.py must pick the same assignment with the same score."""
import json
import os
import shutil
import subprocess
import unittest

from board import data as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node") or os.path.expanduser("~/.local/bin/node")


@unittest.skipUnless(os.path.exists(NODE or ""), "node not installed")
class Parity(unittest.TestCase):
    def test_python_and_javascript_agree(self):
        causes, pageviews, _, _ = D.load_all()
        board = D.compute(causes, pageviews)
        caps = [c["id"] for c in causes["capabilities"]]
        slim = {"capabilities": causes["capabilities"],
                "causes": [{"id": r["id"], "rank": r["rank"], "neglect": r["neglect"], "need": r["need"]} for r in board["causes"]]}
        decls = [({caps[i % 9]: 3, caps[(i * 4) % 9]: 1 + i % 3}, 1 + i % 4, 1 + (i * 3) % 5) for i in range(40)]
        decls += [({}, 1, 1), ({c: 3 for c in caps}, 8, 8), (dict(board["causes"][0]["need"]), 2, 2)]
        script = ("import {assign} from %s;\nconst input = JSON.parse(require_stdin());\n" % json.dumps(os.path.join(ROOT, "site", "assets", "core.js"))
                  ).replace("require_stdin()", "await new Response(process.stdin).text()")
        script += "console.log(JSON.stringify(input.decls.map(([d, r, s]) => assign(input.board, d, r, s).slice(0, 4))));\n"
        res = subprocess.run([NODE, "--input-type=module", "-e", script], input=json.dumps({"board": slim, "decls": decls}),
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        js = json.loads(res.stdout)
        for (d, r, s), got in zip(decls, js):
            want = D.assign(board, caps, d, r, s)[:4]
            self.assertEqual([g["id"] for g in got], [w["id"] for w in want], d)
            for g, w in zip(got, want):
                self.assertAlmostEqual(g["total"], w["total"], places=9)


if __name__ == "__main__":
    unittest.main()
