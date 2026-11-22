import unittest

from board.textutil import has_quote, page_date, page_text

PAGE = """<html><head><title>x</title><script>var a = "1.13 million people died";</script></head><body>
<nav>Home / Fact sheets</nav><h1>Tuberculosis</h1><span>12 November 2026</span><p>Reading time:</p>
<h2>Key facts</h2><ul><li>A total of 1.13&nbsp;million people died from tuberculosis (TB) in 2025.</li>
<li>WHO&rsquo;s report: &ldquo;more than 740&#160;000 people&rdquo;</li></ul><p>Updated 1 December 2027</p></body></html>"""


class Text(unittest.TestCase):
    def test_quote_survives_entities_and_spacing(self):
        text = page_text(PAGE)
        self.assertTrue(has_quote(text, "A total of 1.13 million people died from tuberculosis (TB) in 2025"))
        self.assertTrue(has_quote(text, "WHO's report"))
        self.assertTrue(has_quote(text, "more than 740 000 people"))

    def test_scripts_do_not_count(self):
        self.assertNotIn("var a", page_text(PAGE))

    def test_a_revised_figure_is_not_found(self):
        self.assertFalse(has_quote(page_text(PAGE), "A total of 1.23 million people died"))

    def test_page_date_is_the_one_before_key_facts(self):
        self.assertEqual(page_date(PAGE), "2026-11-12")
        self.assertEqual(page_date("<p>no dates here</p>"), "")


if __name__ == "__main__":
    unittest.main()
