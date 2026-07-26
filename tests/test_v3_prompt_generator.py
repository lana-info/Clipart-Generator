import ast
import tempfile
import unittest
from pathlib import Path

import v3_prompt_generator
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
    generate_into_project,
    generate_prompt_series,
    normalize_generator_data,
    normalize_prompt_entries,
    normalize_prompt_text,
    prompt_generator_defaults,
    replace_project_prompts,
)


class V3PromptGeneratorTests(unittest.TestCase):
    def sample_data(self):
        return PromptGeneratorData(
            theme="Ocean baby animals",
            subjects=["Baby whale", "Baby turtle", "Baby octopus"],
            style="soft watercolor",
            palette="aqua, coral, cream",
            composition="centered full subject",
            background="clean white",
            restrictions=["no text", "no scary expression"],
            count=6,
        )

    def test_same_input_produces_the_same_ordered_series(self):
        first = generate_prompt_series(ProjectMode.CLIPART, self.sample_data())
        second = generate_prompt_series(ProjectMode.CLIPART, self.sample_data())

        self.assertEqual(
            [entry.to_dict() for entry in first],
            [entry.to_dict() for entry in second],
        )
        self.assertEqual(len(first), 6)
        self.assertIn("Baby whale", first[0].prompt)
        self.assertIn("Baby turtle", first[1].prompt)
        self.assertIn("Series item 6 of 6", first[-1].prompt)

    def test_maximum_fields_keep_exact_count_and_required_clauses(self):
        long_value = "x" * MAX_PROMPT_GENERATOR_TEXT_LENGTH
        data = PromptGeneratorData(
            theme=long_value,
            subjects=[long_value],
            style=long_value,
            palette=long_value,
            composition=long_value,
            background=long_value,
            restrictions=[long_value],
            count=3,
        )

        prompts = generate_prompt_series(ProjectMode.CLIPART, data)

        self.assertEqual(len(prompts), 3)
        for index, entry in enumerate(prompts, start=1):
            self.assertIn(f"Series item {index} of 3", entry.prompt)
            self.assertIn("Output intent:", entry.prompt)
            self.assertIn("Restrictions:", entry.prompt)
            self.assertIn("no text", entry.prompt)
    def test_modes_have_distinct_safe_defaults(self):
        clipart = prompt_generator_defaults(ProjectMode.CLIPART)
        pinterest = prompt_generator_defaults(ProjectMode.PINTEREST)

        self.assertIn("isolated", clipart.composition)
        self.assertIn("white background", clipart.background)
        self.assertIn("no text", clipart.restrictions)
        self.assertIn("vertical composition", pinterest.composition)
        self.assertIn("safe zones", pinterest.composition)
        self.assertIn("no mandatory text overlay", pinterest.restrictions)
        self.assertNotEqual(clipart.style, pinterest.style)

    def test_normalization_removes_duplicates_controls_and_bounds_count(self):
        data = PromptGeneratorData(
            theme="  Café\u202e   animals  ",
            subjects=["  Cat  ", "cat", "ＣＡＴ", "\u202eDog"],
            restrictions=["No logo", "no logo", "\u202eNo border"],
            count=MAX_PROMPT_SERIES_COUNT + 50,
        )
        normalized = normalize_generator_data(ProjectMode.PINTEREST, data)
        prompts = generate_prompt_series(ProjectMode.PINTEREST, data)

        self.assertEqual(normalized.theme, "Café animals")
        self.assertEqual(normalized.subjects, ["Cat", "Dog"])
        self.assertNotIn("\u202e", " ".join(normalized.restrictions))
        self.assertEqual(normalized.count, MAX_PROMPT_SERIES_COUNT)
        self.assertEqual(len(prompts), MAX_PROMPT_SERIES_COUNT)

    def test_empty_input_and_processing_mode_fail_clearly(self):
        with self.assertRaisesRegex(PromptGeneratorError, "theme|subject"):
            generate_prompt_series(ProjectMode.CLIPART, PromptGeneratorData())
        with self.assertRaisesRegex(PromptGeneratorError, "only available"):
            prompt_generator_defaults(ProjectMode.PROCESSING)

    def test_results_use_editable_prompt_entry_contract(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        entries = generate_into_project(
            state,
            ProjectMode.CLIPART,
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

    def test_generator_fields_and_manual_edits_survive_project_draft(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        data = self.sample_data()
        generate_into_project(state, ProjectMode.PINTEREST, data)
        state.pinterest.prompts[0].prompt = "Edited after generation"

        with tempfile.TemporaryDirectory(prefix="clipart-v3-generator-") as temp:
            path = Path(temp) / "project.clipart.json"
            save_project_draft(state, path)
            restored = load_project_draft(path)

        self.assertEqual(
            restored.pinterest.prompt_generator.to_dict(),
            normalize_generator_data(
                ProjectMode.PINTEREST,
                data,
            ).to_dict(),
        )
        self.assertEqual(
            restored.pinterest.prompts[0].prompt,
            "Edited after generation",
        )

    def test_old_project_draft_without_generator_section_uses_defaults(self):
        payload = ProjectState(mode=ProjectMode.PINTEREST).to_dict()
        payload["clipart"].pop("prompt_generator")
        payload["pinterest"].pop("prompt_generator")

        restored = ProjectState.from_dict(payload)

        self.assertIn("isolated", restored.clipart.prompt_generator.composition)
        self.assertIn(
            "vertical composition",
            restored.pinterest.prompt_generator.composition,
        )

    def test_invalid_generator_draft_shape_fails_closed(self):
        corruptions = (
            ("subjects", "not-a-list"),
            ("restrictions", [1]),
            ("count", True),
            ("count", 0),
            ("count", MAX_PROMPT_SERIES_COUNT + 1),
            ("theme", "x" * (MAX_PROMPT_GENERATOR_TEXT_LENGTH + 1)),
            ("subjects", ["x"] * (MAX_PROMPT_GENERATOR_ITEMS + 1)),
            ("restrictions", ["x" * (MAX_TEXT_LENGTH + 1)]),
        )
        for key, value in corruptions:
            with self.subTest(key=key):
                payload = ProjectState().to_dict()
                payload["clipart"]["prompt_generator"][key] = value
                with self.assertRaises(ProjectStateError):
                    ProjectState.from_dict(payload)

        payload = ProjectState().to_dict()
        payload["pinterest"]["prompt_generator"]["future"] = True
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
