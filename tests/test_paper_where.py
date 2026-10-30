import unittest

from autoresearch import answer


class PaperWhere(unittest.TestCase):
    """What the agent is told a drawn mark on a paper points at (answer._paper_where)."""

    shape = dict(tool="box", d="M10 20M10 40M5 5H100V60H5Z", bw=680.0, bh=300.0, x=5.0, y=5.0, w=95.0, h=55.0)

    def test_box_names_the_words_inside_and_the_block_size(self):
        s = answer._paper_where(dict(block="hero", quote="43 answers to the goal", prefix="106 / 37 ", suffix="43", shape=self.shape))
        self.assertIn("a box around part of block 'hero'", s)
        self.assertIn("the block is 680 x 300 px", s)
        self.assertIn("1% across and 2% down", s)
        self.assertIn('the words inside it: "43 answers to the goal"', s)

    def test_box_with_no_words_inside_says_so(self):
        s = answer._paper_where(dict(block="hero", quote="Before 1155 Champion 1224", suffix="goal", shape=self.shape))
        self.assertIn('no words inside it; nearest words: "Before 1155 Champion 1224"', s)

    def test_arrow_names_the_word_at_its_tip_with_context(self):
        sh = dict(self.shape, tool="arrow")
        s = answer._paper_where(dict(block="abs-2", quote="92.8%", prefix="On the full\n benchmark it scores ", suffix="92.8%", shape=sh))
        self.assertIn('the word at its tip: "92.8%" (after "...On the full benchmark it scores")', s)
        s = answer._paper_where(dict(block="abs-2", quote="figure words", suffix="near", shape=sh))
        self.assertIn("no word at its tip", s)

    def test_old_marks_and_text_comments_still_read(self):
        old = dict(block="hero", quote="43", shape=dict(tool="pen", d="M475 186.7L519 221.7", bw=686.0, bh=301.7, x=475.0, y=186.7, w=44.0, h=35.0))
        self.assertIn('the words there: "43"', answer._paper_where(old))
        self.assertIn("outside any block", answer._paper_where(dict(quote="Box", shape=dict(tool="box"))))
        self.assertEqual(answer._paper_where(dict(block="b1", quote="hi")), "block 'b1', quoted text: \"hi\"")


if __name__ == "__main__":
    unittest.main()
