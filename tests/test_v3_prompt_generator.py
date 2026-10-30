import ast
import tempfile
import unittest
from pathlib import Path

import v3_prompt_generator
from clipart_prompt_generator import (
    generate_clipart_into_project,
    generate_clipart_prompt_series,
)
from v3_project_state import (
    MAX_PROMPT_GENERATOR_ITEMS,
    MAX_PROMPT_GENERATOR_TEXT_LENGTH,
    MAX_PROMPT_SERIES_COUNT,
    MAX_TEXT_LENGTH,
    ProjectMode,
    ProjectState,
    ProjectStateError,
    PromptEntry,
    PromptGeneratorData,
    load_project_draft,
    save_project_draft,
)
from v3_prompt_generator import (
    PromptGeneratorError,
    generate_prompt_series,
    normalize_generator_data,
    normalize_prompt_entries,
    normalize_prompt_text,
    prompt_generator_defaults,
    replace_project_prompts,
)
from prompt_translation import PromptTranslationResult


class V3PromptGeneratorTests(unittest.TestCase):
    def sample_data(self):
        return PromptGeneratorData(
            theme="Watercolor image from the Ocean baby animals series",
            subjects=["Baby whale", "Baby turtle", "Baby octopus"],
            variations=["holding a shell", "sleeping on a crescent moon"],
            style="soft watercolor",
            palette="aqua, coral, cream",
            composition="centered full subject",
            background="clean white",
            consistency="same visual language and scale",
            restrictions=["no text", "no scary expression"],
        )

    def test_optional_translation_backend_is_used_for_provider_prompt(self):
        class FakeTranslator:
            backend_id = "test-translator"

            def translate_fields(self, fields, *, source_language, target_language):
                translated = dict(fields)
                translated["object"] = "fox"
                return PromptTranslationResult(
                    source_language=source_language,
                    target_language=target_language,
                    translated=True,
                    fields=translated,
                    backend_id=self.backend_id,
                )

        prompts = generate_clipart_prompt_series(
            PromptGeneratorData(subjects=["лиса"]),
            translation_backend=FakeTranslator(),
            provider_language="en",
        )

        self.assertIn("Object: fox.", prompts[0].prompt)
        self.assertNotIn("Объект:", prompts[0].prompt)

    def test_same_input_produces_the_same_ordered_series(self):
        first = generate_clipart_prompt_series(self.sample_data())
        second = generate_clipart_prompt_series(self.sample_data())

        self.assertEqual(
            [entry.to_dict() for entry in first],
            [entry.to_dict() for entry in second],
        )
        self.assertEqual(len(first), 6)
        self.assertIn("Baby whale", first[0].prompt)
        self.assertIn("holding a shell", first[0].prompt)
        self.assertIn("sleeping on a crescent moon", first[1].prompt)
        self.assertIn("Baby turtle", first[2].prompt)
        self.assertNotIn("Series item", first[-1].prompt)

    def test_clipart_prompt_uses_structured_sections_for_provider_prompt(self):
        prompts = generate_clipart_prompt_series(
            PromptGeneratorData(
                theme="весенняя коллекция",
                subjects=["лиса"],
                variations=["с букетом", "с корзинкой"],
                style="мягкая акварель",
                palette="персиковый, шалфейный, кремовый",
                composition="по центру, отдельный объект",
                background="прозрачный",
                restrictions=["без текста", "без водяного знака"],
            ),
        )

        self.assertIn("Объект:", prompts[0].prompt)
        self.assertIn("Сцена:", prompts[0].prompt)
        self.assertIn("Цветовая палитра:", prompts[0].prompt)
        self.assertIn("Ограничения:", prompts[0].prompt)
        self.assertIn("с букетом", prompts[0].prompt)
        self.assertIn("с корзинкой", prompts[1].prompt)

    def test_clipart_prompt_can_add_local_chroma_key_instructions(self):
        prompts = generate_clipart_prompt_series(
            PromptGeneratorData(
                subjects=["winter wreath"],
                style="watercolor",
                chroma_key_enabled=True,
                chroma_key_color="blue",
            ),
        )

        self.assertIn("#0000FF", prompts[0].prompt)
        self.assertIn("no paper texture", prompts[0].prompt)
        self.assertEqual(prompts[0].chroma_key_color, "blue")

    def test_clipart_series_chooses_key_per_prompt_without_manual_default(self):
        prompts = generate_clipart_prompt_series(
            PromptGeneratorData(
                subjects=["blue ribbon with green leaves"],
                chroma_key_enabled=True,
                chroma_key_color="blue",
            ),
        )

        self.assertEqual(prompts[0].chroma_key_color, "red")
        self.assertIn("#FF0000", prompts[0].prompt)
        self.assertNotIn("#0000FF", prompts[0].prompt)

    def test_clipart_series_keeps_selected_chroma_materials(self):
        prompts = generate_clipart_prompt_series(
            PromptGeneratorData(
                subjects=["eucalyptus branch"],
                chroma_key_enabled=True,
                chroma_key_color="blue",
                chroma_key_materials=["thin_leaves"],
            ),
        )

        self.assertIn("thick flat blades", prompts[0].prompt)

    def test_chroma_material_selection_keeps_at_most_three_materials(self):
        data = PromptGeneratorData(
            chroma_key_materials=[
                "watercolor",
                "thin_leaves",
                "metal",
                "snow_ice",
            ],
        )

        self.assertEqual(
            data.chroma_key_materials,
            ["watercolor", "thin_leaves", "metal"],
        )

    def test_chroma_key_generator_settings_survive_project_draft(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompt_generator.chroma_key_enabled = True
        state.clipart.prompt_generator.chroma_key_color = "red"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft.json"
            save_project_draft(state, path)
            restored = load_project_draft(path)
        self.assertTrue(restored.clipart.prompt_generator.chroma_key_enabled)
        self.assertEqual(restored.clipart.prompt_generator.chroma_key_color, "red")

    def test_invalid_chroma_key_color_is_rejected_from_project_draft(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompt_generator.chroma_key_color = "not-a-color"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProjectStateError):
                save_project_draft(state, Path(directory) / "draft.json")

    def test_generated_prompt_contains_only_user_entered_text(self):
        long_value = "x" * 100
        data = PromptGeneratorData(
            theme=long_value,
            subjects=[long_value],
            variations=["sitting with flowers"],
            style=long_value,
            palette=long_value,
            composition=long_value,
            background=long_value,
            consistency=long_value,
            restrictions=[long_value],
        )

        prompts = generate_clipart_prompt_series(data)

        self.assertEqual(len(prompts), 1)
        prompt = prompts[0].prompt
        self.assertIn("sitting with flowers", prompt)
        for hidden_text in (
            "Output intent",
            "Series item",
            "Series consistency",
            "Theme:",
            "Subject or scene:",
            "clipart",
        ):
            self.assertNotIn(hidden_text, prompt)
        self.assertIn("Object:", prompt)
        self.assertIn("Color palette:", prompt)
        self.assertIn("Restrictions:", prompt)

    def test_empty_optional_fields_are_skipped_and_empty_variations_use_each_object_once(self):
        data = PromptGeneratorData(
            theme="Children's illustration",
            subjects=["Fox", "Bear"],
            style="soft watercolor",
        )

        prompts = generate_prompt_series(ProjectMode.PINTEREST, data)

        self.assertEqual(
            [entry.prompt for entry in prompts],
            [
                "Children's illustration. Fox. soft watercolor.",
                "Children's illustration. Bear. soft watercolor.",
            ],
        )
    def test_modes_start_with_empty_visible_fields(self):
        clipart = prompt_generator_defaults(ProjectMode.CLIPART)
        pinterest = prompt_generator_defaults(ProjectMode.PINTEREST)

        self.assertEqual(clipart.to_dict(), PromptGeneratorData().to_dict())
        self.assertEqual(pinterest.to_dict(), PromptGeneratorData().to_dict())

    def test_normalization_preserves_entered_rows_and_unicode_while_removing_controls(self):
        data = PromptGeneratorData(
            theme="  Café\u202e   animals  ",
            subjects=["  Cat  ", "cat", "ＣＡＴ", "\u202eDog"],
            restrictions=["No logo", "no logo", "\u202eNo border"],
            variations=[" Front view ", "front view", "Side view"],
        )
        normalized = normalize_generator_data(ProjectMode.PINTEREST, data)
        prompts = generate_prompt_series(ProjectMode.PINTEREST, data)

        self.assertEqual(normalized.theme, "Café animals")
        self.assertEqual(normalized.subjects, ["Cat", "cat", "ＣＡＴ", "Dog"])
        self.assertEqual(
            normalized.variations,
            ["Front view", "front view", "Side view"],
        )
        self.assertNotIn("\u202e", " ".join(normalized.restrictions))
        self.assertEqual(len(prompts), 12)

    def test_cartesian_product_preserves_duplicate_rows_even_when_punctuation_matches(self):
        data = PromptGeneratorData(
            subjects=["cat.", "cat"],
            variations=["sitting"],
        )

        prompts = generate_clipart_prompt_series(data)

        self.assertEqual(
            [entry.prompt for entry in prompts],
            [
                "Object: cat.. Details: sitting.",
                "Object: cat. Details: sitting.",
            ],
        )

    def test_empty_input_and_processing_mode_fail_clearly(self):
        with self.assertRaisesRegex(PromptGeneratorError, "field|object"):
            generate_clipart_prompt_series(PromptGeneratorData())
        with self.assertRaisesRegex(PromptGeneratorError, "only available"):
            prompt_generator_defaults(ProjectMode.PROCESSING)

    def test_results_use_editable_prompt_entry_contract(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        entries = generate_clipart_into_project(
            state,
            self.sample_data(),
        )

        self.assertIs(entries, state.clipart.prompts)
        self.assertTrue(all(isinstance(entry, PromptEntry) for entry in entries))
        entries[0].prompt = "Manually edited whale"
        entries[0].references.append("D:/whale.png")
        self.assertEqual(state.clipart.prompts[0].prompt, "Manually edited whale")
        self.assertEqual(
            state.clipart.prompts[0].references,
            ["D:/whale.png"],
        )

    def test_normalized_manual_edits_deduplicate_and_preserve_references(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        result = replace_project_prompts(
            state,
            ProjectMode.PINTEREST,
            [
                {"prompt": "  Summer   pin  ", "references": ["D:/one.png"]},
                {"prompt": "summer pin", "references": ["D:/two.png"]},
                {"prompt": "\u202eSecond pin", "references": []},
                {"prompt": " ", "references": []},
            ],
        )

        self.assertEqual(
            [entry.prompt for entry in result],
            ["Summer pin", "Second pin"],
        )
        self.assertEqual(result[0].references, ["D:/one.png"])

    def test_csv_replacement_can_preserve_repeated_prompt_rows(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        result = replace_project_prompts(
            state,
            ProjectMode.CLIPART,
            [PromptEntry("Same prompt"), PromptEntry("same prompt")],
            deduplicate=False,
        )

        self.assertEqual([entry.prompt for entry in result], ["Same prompt", "same prompt"])

    def test_generator_fields_and_manual_edits_survive_project_draft(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        data = self.sample_data()
        generate_clipart_into_project(state, data)
        state.clipart.prompts[0].prompt = "Edited after generation"

        with tempfile.TemporaryDirectory(prefix="clipart-v3-generator-") as temp:
            path = Path(temp) / "project.clipart.json"
            save_project_draft(state, path)
            restored = load_project_draft(path)

        self.assertEqual(
            restored.clipart.prompt_generator.to_dict(),
            normalize_generator_data(
                ProjectMode.CLIPART,
                data,
            ).to_dict(),
        )
        self.assertEqual(
            restored.clipart.prompts[0].prompt,
            "Edited after generation",
        )

    def test_old_project_draft_without_generator_section_uses_defaults(self):
        payload = ProjectState(mode=ProjectMode.PINTEREST).to_dict()
        payload["clipart"].pop("prompt_generator")

        restored = ProjectState.from_dict(payload)

        self.assertEqual(restored.clipart.prompt_generator, PromptGeneratorData())

    def test_invalid_generator_draft_shape_fails_closed(self):
        corruptions = (
            ("subjects", "not-a-list"),
            ("variations", "not-a-list"),
            ("restrictions", [1]),
            ("count", True),
            ("count", 0),
            ("count", MAX_PROMPT_SERIES_COUNT + 1),
            ("theme", "x" * (MAX_PROMPT_GENERATOR_TEXT_LENGTH + 1)),
            ("subjects", ["x"] * (MAX_PROMPT_GENERATOR_ITEMS + 1)),
            ("variations", ["x"] * (MAX_PROMPT_GENERATOR_ITEMS + 1)),
            ("restrictions", ["x" * (MAX_TEXT_LENGTH + 1)]),
        )
        for key, value in corruptions:
            with self.subTest(key=key):
                payload = ProjectState().to_dict()
                payload["clipart"]["prompt_generator"][key] = value
                with self.assertRaises(ProjectStateError):
                    ProjectState.from_dict(payload)


    def test_generator_module_has_no_network_client_imports(self):
        source = Path(v3_prompt_generator.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            imported_roots.isdisjoint(
                {"requests", "urllib", "httpx", "aiohttp", "socket"}
            )
        )


    def test_public_normalizers_bound_invalid_inputs(self):
        self.assertEqual(normalize_prompt_entries("one prompt"), [])
        self.assertEqual(normalize_prompt_entries(None), [])
        with self.assertRaises(TypeError):
            normalize_prompt_entries([], limit=True)
        with self.assertRaises(ValueError):
            normalize_prompt_text("text", limit=0)

        oversized = "x" * 100_000
        self.assertEqual(len(normalize_prompt_text(oversized, limit=100)), 100)
if __name__ == "__main__":
    unittest.main()
