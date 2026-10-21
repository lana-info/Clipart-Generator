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
        self.assertEqual(choice.color, "red")
        self.assertEqual(choice.avoided_terms, ())

    def test_explicit_red_and_green_subject_prefers_blue(self):
        choice = select_chroma_key_color("red roses with green leaves")
        self.assertEqual(choice.color, "blue")

    def test_flowers_imply_leaves_so_green_is_not_chosen(self):
        for text in ("cute duckling with pink party hat, daisy flowers, blue ribbon bow",
                     "утёнок в розовой шапке с ромашками и голубым бантом"):
            self.assertNotEqual(select_chroma_key_color(text).color, "green", text)

    def test_trees_and_greenery_imply_green_so_it_is_avoided(self):
        for text in ("pink gnome with a small christmas tree", "блестящая ёлка с розовым бантом",
                     "owl on a pine branch with a blue scarf", "котик в кустах и розовой шапке"):
            self.assertNotEqual(select_chroma_key_color(text).color, "green", text)

    def test_unrelated_words_with_similar_stems_do_not_count_as_greenery(self):
        for text in ("fluffy duckling", "мохнатый утёнок", "a fire truck"):
            self.assertEqual(select_chroma_key_color(text).color, "blue", text)

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
