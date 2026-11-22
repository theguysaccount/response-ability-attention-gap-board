"""The editorial and machine data files, and the board computation. Never pins launch-day counts or names."""
import copy
import math
import unittest

from board import data as D


class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.causes, cls.pageviews, cls.sources, cls.record = D.load_all()
        cls.board = D.compute(cls.causes, cls.pageviews)
        cls.caps = [c["id"] for c in cls.causes["capabilities"]]

    def test_files_validate(self):
        self.assertEqual(D.validate_causes(self.causes), [])
        self.assertEqual(D.validate_pageviews(self.causes, self.pageviews), [])

    def test_board_is_sorted_and_ranked(self):
        vpd = [r["vpd"] for r in self.board["causes"]]
        self.assertEqual(vpd, sorted(vpd))
        self.assertEqual([r["rank"] for r in self.board["causes"]], list(range(1, len(vpd) + 1)))

    def test_neglect_index_runs_from_one(self):
        neglect = [r["neglect"] for r in self.board["causes"]]
        self.assertAlmostEqual(min(neglect), 1.0)
        self.assertEqual(neglect, sorted(neglect, reverse=True))
        top = self.board["causes"][0]
        self.assertAlmostEqual(top["neglect"], math.log10(top["deaths"] / top["views"]) - math.log10(
            self.board["causes"][-1]["deaths"] / self.board["causes"][-1]["views"]) + 1)

    def test_views_are_the_sum_of_listed_articles(self):
        for r in self.board["causes"] + [self.board["reference"]]:
            self.assertEqual(r["views"], sum(v for _, v in r["per_article"]))
            self.assertEqual(len(r["monthly"]), 12)
            self.assertEqual(sum(r["monthly"]), r["views"])

    def test_reference_is_never_ranked(self):
        self.assertIsNone(self.board["reference"]["rank"])
        self.assertNotIn(self.board["reference"]["id"], [r["id"] for r in self.board["causes"]])

    def test_a_specialist_is_routed_to_the_cause_shaped_like_them(self):
        for cause in self.board["causes"]:
            ranked = D.assign(self.board, self.caps, cause["need"], 1, 1)
            mine = [s for s in ranked if s["id"] == cause["id"]][0]
            self.assertAlmostEqual(mine["fit"], 1.0)

    def test_rarity_and_scale_never_change_the_winner(self):
        decl = {self.caps[0]: 3, self.caps[3]: 1}
        a = [s["id"] for s in D.assign(self.board, self.caps, decl, 1, 1)]
        b = [s["id"] for s in D.assign(self.board, self.caps, decl, 8, 8)]
        self.assertEqual(a, b)

    def test_no_declaration_scores_zero_everywhere(self):
        ranked = D.assign(self.board, self.caps, {}, 4, 4)
        self.assertTrue(all(s["total"] == 0 for s in ranked))
        self.assertEqual(ranked[0]["id"], self.board["causes"][0]["id"])   # ties go to the most neglected


class Validation(unittest.TestCase):
    def setUp(self):
        self.causes = D.read_json("causes.json")

    def broken(self, mutate):
        c = copy.deepcopy(self.causes)
        mutate(c)
        return D.validate_causes(c)

    def test_long_quotes_are_refused(self):
        self.assertTrue(self.broken(lambda c: c["causes"][0]["source"].update(quote=" ".join(["word"] * 16))))

    def test_range_midpoint_is_enforced(self):
        def bad(c):
            row = c["causes"][0]
            row.update(bound="range", deaths_low=10, deaths_high=30, deaths=25)
        self.assertTrue(self.broken(bad))

    def test_article_counted_twice_is_refused(self):
        def dup(c):
            c["causes"][1]["articles"] = list(c["causes"][0]["articles"][:1])
        self.assertTrue(self.broken(dup))

    def test_need_must_cover_every_capability(self):
        self.assertTrue(self.broken(lambda c: c["causes"][0]["need"].pop(next(iter(c["causes"][0]["need"])))))

    def test_https_sources_only(self):
        self.assertTrue(self.broken(lambda c: c["causes"][0]["source"].update(url="http://example.org/x")))

    def test_support_links_are_required(self):
        self.assertTrue(self.broken(lambda c: c["support"].update(links=[])))


if __name__ == "__main__":
    unittest.main()
