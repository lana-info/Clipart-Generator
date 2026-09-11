import unittest

from chroma_key_selection import select_chroma_key_color


class ChromaKeySelectionTests(unittest.TestCase):
    def test_empty_or_neutral_text_keeps_established_blue_default(self):
        choice = select_chroma_key_color("cute ceramic animal")
        self.assertEqual(choice.color, "blue")
        self.assertEqual(choice.confidence, "text_only")
        self.assertEqual(choice.rgb, (0, 0, 255))

    def test_explicit_blue_subject_avoids_blue(self):
        choice = select_chroma_key_color("blue ribbon and turquoise hat")
        self.assertEqual(choice.color, "green")
        self.assertEqual(choice.avoided_terms, ())

    def test_explicit_red_and_green_subject_prefers_blue(self):
        choice = select_chroma_key_color("red roses with green leaves")
        self.assertEqual(choice.color, "blue")

    def test_russian_word_stems_are_considered(self):
        choice = select_chroma_key_color("зелёные листья и голубая лента")
        self.assertEqual(choice.color, "red")

    def test_all_choices_are_a_heuristic_not_a_false_guarantee(self):
        choice = select_chroma_key_color("red rose, green leaf, blue ribbon")
        self.assertEqual(choice.color, "blue")
        self.assertEqual(choice.confidence, "low")
        self.assertIn("blue", choice.avoided_terms)

    def test_iterable_input_and_invalid_scalar(self):
        self.assertEqual(select_chroma_key_color(("blue ribbon", "green leaf")).color, "red")
        with self.assertRaises(TypeError):
            select_chroma_key_color(17)


if __name__ == "__main__":
    unittest.main()
