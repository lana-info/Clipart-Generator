import copy
import json
import tempfile
import unittest
from pathlib import Path

from v3_project_state import (
    MAX_DRAFT_BYTES,
    PROJECT_STATE_SCHEMA_VERSION,
    ClipartModeData,
    CommonProjectData,
    GenerationData,
    ImageOperationData,
    PinterestPinData,
    PinterestPinResultData,
    PinterestModeData,
    ProcessingModeData,
    ProjectMode,
    ProjectState,
    ProjectStateError,
    ProjectStateValidationError,
    PromptEntry,
    StepId,
    load_project_draft,
    migrate_v2_config,
    route_for_mode,
    save_project_draft,
)


class ProjectRoutesTests(unittest.TestCase):
    def test_legacy_topaz_settings_migrate_to_current_contract(self):
        operations = ImageOperationData(
            upscale_factor=8,
            kie_upscale_model="topaz/upscale",
            kie_upscale_after_model="topaz/upscale",
        )
        self.assertEqual(operations.upscale_factor, 4)
        self.assertEqual(operations.kie_upscale_model, "topaz/image-upscale")
        self.assertEqual(
            operations.kie_upscale_after_model,
            "topaz/image-upscale",
        )
        self.assertEqual(ImageOperationData(upscale_factor=1).upscale_factor, 2)
        for invalid_factor in (True, 1.5, "1.5", 8, None):
            with self.subTest(invalid_factor=invalid_factor):
                self.assertEqual(
                    ImageOperationData(upscale_factor=invalid_factor).upscale_factor,
                    4,
                )

    def test_processing_collision_policy_round_trips_through_state(self):
        state = ProjectState(
            mode=ProjectMode.PROCESSING,
            processing=ProcessingModeData(overwrite_existing=True),
        )
        restored = ProjectState.from_dict(state.to_dict())
        self.assertTrue(restored.processing.overwrite_existing)

    def test_each_mode_has_a_stable_ordered_route(self):
        self.assertEqual(
            route_for_mode(ProjectMode.CLIPART),
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PROMPT_REVIEW,
                StepId.GENERATION,
                StepId.PROCESSING_OPTIONS,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
                StepId.TRANSPARENCY,
            ),
        )
        self.assertEqual(
            route_for_mode(ProjectMode.PINTEREST),
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PROMPT_REVIEW,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )
        self.assertEqual(
            route_for_mode(ProjectMode.PROCESSING),
            (
                StepId.FILES,
                StepId.GOAL,
                StepId.PIPELINE,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
                StepId.TRANSPARENCY,
            ),
        )

    def test_forward_validation_and_back_navigation_preserve_mode_data(self):
        state = ProjectState()
        with self.assertRaises(ProjectStateValidationError):
            state.next_step()
        self.assertEqual(state.current_step, StepId.PROJECT)

        state.common.work_dir = "D:/work"
        self.assertEqual(state.next_step(), StepId.PROMPTS)
        state.clipart.prompts.append(PromptEntry("blue whale"))
        self.assertEqual(state.next_step(), StepId.PROMPT_REVIEW)
        state.clipart.prompts[0].prompt = "small blue whale"
        self.assertEqual(state.next_step(), StepId.GENERATION)
        self.assertEqual(state.previous_step(), StepId.PROMPT_REVIEW)
        self.assertEqual(state.previous_step(), StepId.PROMPTS)
        self.assertEqual(state.clipart.prompts[0].prompt, "small blue whale")

    def test_switching_modes_preserves_independent_steps_and_settings(self):
        state = ProjectState(
            common=CommonProjectData(work_dir="D:/work"),
            clipart=ClipartModeData(prompts=[PromptEntry("fox")]),
            pinterest=PinterestModeData(),
            processing=ProcessingModeData(selected_files=["D:/input.png"]),
        )
        state.next_step()
        self.assertEqual(state.current_step, StepId.PROMPTS)

        state.switch_mode(ProjectMode.PINTEREST)
        self.assertEqual(state.current_step, StepId.PROJECT)
        state.next_step()
        self.assertEqual(state.current_step, StepId.PROMPTS)

        state.switch_mode(ProjectMode.PROCESSING)
        self.assertEqual(state.next_step(), StepId.GOAL)
        state.switch_mode(ProjectMode.CLIPART)
        self.assertEqual(state.current_step, StepId.PROMPTS)
        self.assertEqual(state.clipart.prompts[0].prompt, "fox")
        self.assertEqual(state.pinterest.generation.ratio, "2:3")

    def test_rejects_a_step_from_another_mode(self):
        state = ProjectState()
        with self.assertRaises(ProjectStateError):
            state.set_step(StepId.FILES)


class ProjectSerializationTests(unittest.TestCase):
    def test_saved_transparency_editor_step_reopens_on_results_without_a_session(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.set_step(StepId.TRANSPARENCY)

        restored = ProjectState.from_dict(state.to_dict())

        self.assertIs(
            restored.current_step_by_mode[ProjectMode.CLIPART],
            StepId.RESULTS,
        )

    def test_pinterest_pin_draft_defaults_are_serializable(self):
        draft = PinterestPinData()

        self.assertEqual(draft.canvas_width, 1000)
        self.assertEqual(draft.canvas_height, 1500)
        self.assertEqual(draft.template_count, 3)
        self.assertEqual(draft.ai_scene_count, 3)
        self.assertEqual(draft.product_paths, [])
        self.assertEqual(draft.selected_product_index, 0)
        self.assertEqual(draft.pin_title, "")
        self.assertEqual(draft.pin_subtitle, "")
        self.assertEqual(draft.pin_cta, "")
        self.assertEqual(draft.style, "")
        self.assertEqual(draft.background_description, "")
        self.assertEqual(draft.color_palette, "")
        self.assertEqual(
            PinterestPinData.from_dict(draft.to_dict()).to_dict(),
            draft.to_dict(),
        )

    def test_clean_pinterest_project_uses_prompt_only_canonical_state_and_route(self):
        """A new Pinterest project persists prompts without the future pin workflow."""
        state = ProjectState(mode=ProjectMode.PINTEREST)
        payload = state.to_dict()

        self.assertEqual(
            state.route,
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PROMPT_REVIEW,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )
        self.assertEqual(
            set(payload["pinterest"]),
            {"prompts", "generation", "pin", "results"},
        )
        self.assertNotIn("pinterest_legacy", payload)

    def test_legacy_pinterest_extras_are_archived_while_prompts_stay_canonical(self):
        """Prompt-only drafts keep prompts active and archive removed generator fields."""
        payload = ProjectState(mode=ProjectMode.PINTEREST).to_dict()
        payload["pinterest"].update(
            {
                "prompts": [{"prompt": "legacy summer pin", "references": []}],
                "prompt_generator": {
                    "theme": "summer",
                    "subjects": ["bag"],
                    "variations": ["bright"],
                    "style": "editorial",
                    "palette": "warm",
                    "composition": "vertical",
                    "background": "studio",
                    "consistency": "",
                    "restrictions": [],
                    "count": 1,
                },
            }
        )

        restored = ProjectState.from_dict(payload)
        migrated = restored.to_dict()

        self.assertEqual(
            migrated["pinterest"]["prompts"],
            [{"prompt": "legacy summer pin", "references": []}],
        )
        self.assertNotIn("prompt_generator", migrated["pinterest"])
        self.assertEqual(
            migrated["pinterest_legacy"]["prompts"],
            [],
        )

    def test_pinterest_pin_draft_normalizes_bounds_and_selected_product(self):
        draft = PinterestPinData(
            canvas_width=0,
            canvas_height=99999,
            template_count=0,
            ai_scene_count=99,
            product_paths=["  D:/one.png  ", "", "D:/two.png"],
            selected_product_index=99,
        )

        self.assertEqual(draft.canvas_width, 1000)
        self.assertEqual(draft.canvas_height, 1500)
        self.assertEqual(draft.template_count, 3)
        self.assertEqual(draft.ai_scene_count, 3)
        self.assertEqual(draft.product_paths, ["D:/one.png", "D:/two.png"])
        self.assertEqual(draft.selected_product_index, 1)

    def test_pinterest_pin_results_round_trip_as_metadata_without_image_bytes(self):
        state = ProjectState(
            mode=ProjectMode.PINTEREST,
            pinterest=PinterestModeData(
                pin=PinterestPinData(
                    product_paths=["D:/product.png"],
                    pin_title="Summer collection",
                ),
                results=[
                    PinterestPinResultData(
                        variant_id="template-1",
                        variant_kind="template",
                        source_product_path="D:/product.png",
                        output_path="D:/output/template-1.png",
                        accepted=True,
                        status="success",
                        retryable=False,
                        product_layer_digest="abc123",
                        export_status="exported",
                    ),
                    PinterestPinResultData(
                        variant_id="scene-1",
                        variant_kind="ai_scene",
                        source_product_path="D:/product.png",
                        status="failed",
                        retryable=True,
                        product_layer_digest="abc123",
                        error_code="background_generation_failed",
                        error_message="Не удалось создать фон. Повторите попытку.",
                    ),
                ],
            ),
        )

        payload = state.to_dict()
        restored = ProjectState.from_dict(payload)

        self.assertEqual(restored.to_dict(), payload)
        self.assertNotIn("image", payload["pinterest"]["results"][0])
        self.assertEqual(
            restored.pinterest.results[1].error_code,
            "background_generation_failed",
        )

    def test_pinterest_result_replaces_raw_provider_error_with_safe_fallback(self):
        result = PinterestPinResultData(
            status="failed",
            error_code="provider_http_502",
            error_message="Fal.ai HTTP 502; api_key=demo-provider-token",
        )

        metadata = result.to_dict()

        self.assertEqual(metadata["error_code"], "pin_generation_failed")
        self.assertEqual(
            metadata["error_message"],
            "Не удалось создать вариант пина. Повторите попытку.",
        )
        self.assertNotIn("demo-provider-token", metadata["error_message"])

    def test_project_draft_rejects_unknown_pinterest_error_code_and_raw_message(self):
        for error_code, error_message in (
            ("provider_http_502", ""),
            (
                "background_generation_failed",
                "Fal.ai HTTP 502; api_key=demo-provider-token",
            ),
        ):
            with self.subTest(error_code=error_code):
                payload = ProjectState(
                    mode=ProjectMode.PINTEREST,
                    pinterest=PinterestModeData(
                        results=[
                            PinterestPinResultData(
                                status="failed",
                                error_code="background_generation_failed",
                            )
                        ]
                    ),
                ).to_dict()
                result = payload["pinterest"]["results"][0]
                result["error_code"] = error_code
                result["error_message"] = error_message

                with self.assertRaises(ProjectStateError):
                    ProjectState.from_dict(payload)

    def test_save_project_draft_rejects_mutated_unsafe_pinterest_error(self):
        state = ProjectState(
            mode=ProjectMode.PINTEREST,
            pinterest=PinterestModeData(
                results=[
                    PinterestPinResultData(
                        status="failed",
                        error_code="background_generation_failed",
                    )
                ]
            ),
        )
        result = state.pinterest.results[0]
        result.error_code = "provider_http_502"
        result.error_message = "Fal.ai HTTP 502; api_key=demo-provider-token"

        with tempfile.TemporaryDirectory(prefix="pinterest-v3-unsafe-save-") as temp_dir:
            path = Path(temp_dir) / "project.json"

            with self.assertRaises(ProjectStateError):
                save_project_draft(state, path)

            self.assertFalse(path.exists())

    def test_old_pinterest_project_loads_with_new_pin_defaults(self):
        payload = ProjectState(mode=ProjectMode.PINTEREST).to_dict()
        del payload["pinterest"]["pin"]
        del payload["pinterest"]["results"]

        restored = ProjectState.from_dict(payload)

        self.assertEqual(restored.pinterest.pin, PinterestPinData())
        self.assertEqual(restored.pinterest.results, [])

    def test_pinterest_draft_discards_legacy_cleanup_and_background_fields(self):
        payload = ProjectState(mode=ProjectMode.PINTEREST).to_dict()
        payload["pinterest"]["operations"] = (
            {
                "remove_background": True,
                "remove_background_provider": "local_rembg",
                "trim": True,
                "remove_exif": True,
                "visible_mark_cleanup": True,
            }
        )

        restored = ProjectState.from_dict(payload)
        self.assertNotIn("operations", restored.to_dict()["pinterest"])
        self.assertEqual(
            restored.to_dict()["pinterest_legacy"]["operations"],
            payload["pinterest"]["operations"],
        )

    def test_project_draft_rejects_invalid_pinterest_dimensions_and_counts(self):
        for field, invalid_value in (
            ("canvas_width", 999),
            ("canvas_height", 1499),
            ("template_count", 2),
            ("ai_scene_count", 4),
        ):
            with self.subTest(field=field):
                payload = ProjectState(mode=ProjectMode.PINTEREST).to_dict()
                payload["pinterest"]["pin"][field] = invalid_value

                with self.assertRaises(ProjectStateError):
                    ProjectState.from_dict(payload)

    def complete_state(self):
        return ProjectState(
            mode=ProjectMode.PINTEREST,
            common=CommonProjectData(
                project_name="Summer",
                work_dir="D:/work",
                output_dir="D:/work/output",
            ),
            clipart=ClipartModeData(
                prompts=[PromptEntry("shell", ["D:/ref.png"])],
                generation=GenerationData(
                    model="gpt-image-2",
                    ratio="1:1",
                    resolution="2K",
                    variants=2,
                ),
            ),
            pinterest=PinterestModeData(
                generation=GenerationData(
                    model="nano-banana-2",
                    ratio="9:16",
                    resolution="2K",
                    variants=3,
                ),
            ),
            processing=ProcessingModeData(
                selected_files=["D:/one.png", "D:/two.png"],
                recipe="prepare_clipart",
            ),
            current_step_by_mode={
                ProjectMode.CLIPART: StepId.GENERATION,
                ProjectMode.PINTEREST: StepId.PROMPTS,
                ProjectMode.PROCESSING: StepId.PIPELINE,
            },
        )

    def test_round_trip_preserves_all_mode_specific_data(self):
        source = self.complete_state()
        restored = ProjectState.from_dict(source.to_dict())
        self.assertEqual(restored.to_dict(), source.to_dict())
        self.assertEqual(restored.current_step, StepId.PROMPTS)

    def test_clipart_mode_starts_with_clipart_specific_defaults(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        self.assertTrue(state.clipart.operations.upscale_before)
        self.assertTrue(state.clipart.operations.remove_background)
        self.assertTrue(state.clipart.operations.trim)
        self.assertTrue(state.clipart.operations.export_300_dpi)

    def test_atomic_draft_save_and_load(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-draft-") as temp_dir:
            path = Path(temp_dir) / "project.clipart.json"
            source = self.complete_state()
            save_project_draft(source, path)
            restored = load_project_draft(path)
            self.assertEqual(restored.to_dict(), source.to_dict())

    def test_mode_specific_output_and_processing_consent_survive_restart(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-preferences-") as temp_dir:
            source = ProjectState()
            source.set_output_dir_for_mode("D:/clipart", ProjectMode.CLIPART)
            source.set_output_dir_for_mode("D:/pinterest", ProjectMode.PINTEREST)
            source.set_output_dir_for_mode("D:/processing", ProjectMode.PROCESSING)
            source.processing.recipe = "metadata_cleanup"
            source.processing.deep_watermark_consent = True
            path = Path(temp_dir) / "project_state.json"
            save_project_draft(source, path)

            restored = load_project_draft(path)
            self.assertEqual(restored.output_dir_for_mode(ProjectMode.CLIPART), "D:/clipart")
            self.assertEqual(restored.output_dir_for_mode(ProjectMode.PINTEREST), "D:/pinterest")
            self.assertEqual(restored.output_dir_for_mode(ProjectMode.PROCESSING), "D:/processing")
            self.assertEqual(restored.processing.recipe, "metadata_cleanup")
            self.assertTrue(restored.processing.deep_watermark_consent)
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_invalid_or_oversized_drafts_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-invalid-") as temp_dir:
            root = Path(temp_dir)
            invalid = root / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            with self.assertRaises(ProjectStateError):
                load_project_draft(invalid)

            unsupported = root / "unsupported.json"
            unsupported.write_text(
                json.dumps({"schema_version": PROJECT_STATE_SCHEMA_VERSION + 1}),
                encoding="utf-8",
            )
            with self.assertRaises(ProjectStateError):
                load_project_draft(unsupported)

            for invalid_version in (True, 1.0):
                unsupported.write_text(
                    json.dumps({"schema_version": invalid_version}),
                    encoding="utf-8",
                )
                with self.assertRaises(ProjectStateError):
                    load_project_draft(unsupported)

            deeply_nested = root / "deep.json"
            deeply_nested.write_text("[" * 1200 + "0" + "]" * 1200, encoding="utf-8")
            with self.assertRaises(ProjectStateError):
                load_project_draft(deeply_nested)

            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (MAX_DRAFT_BYTES + 1))
            with self.assertRaises(ProjectStateError):
                load_project_draft(oversized)


    def test_unknown_versioned_draft_fields_fail_closed(self):
        payloads = []

        root = self.complete_state().to_dict()
        root["future"] = True
        payloads.append(root)

        common = self.complete_state().to_dict()
        common["common"]["future"] = True
        payloads.append(common)

        runtime = self.complete_state().to_dict()
        runtime["runtime"]["future"] = True
        payloads.append(runtime)

        mode_section = self.complete_state().to_dict()
        mode_section["clipart"]["future"] = True
        payloads.append(mode_section)

        prompt = self.complete_state().to_dict()
        prompt["clipart"]["prompts"][0]["future"] = True
        payloads.append(prompt)

        generation = self.complete_state().to_dict()
        generation["clipart"]["generation"]["future"] = True
        payloads.append(generation)

        operations = self.complete_state().to_dict()
        operations["processing"]["operations"]["future"] = True
        payloads.append(operations)

        steps = self.complete_state().to_dict()
        steps["current_step_by_mode"]["future"] = "project"
        payloads.append(steps)

        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                with self.assertRaises(ProjectStateError):
                    ProjectState.from_dict(payload)

    def test_untrusted_boolean_strings_do_not_enable_operations(self):
        payload = self.complete_state().to_dict()
        payload["clipart"]["operations"]["visible_mark_cleanup"] = "false"
        payload["clipart"]["operations"]["upscale_before"] = "false"
        with self.assertRaises(ProjectStateError):
            ProjectState.from_dict(payload)

    def test_known_draft_sections_fail_closed_on_invalid_types(self):
        corruptions = (
            ("clipart", []),
            ("processing", "bad"),
            ("current_step_by_mode", []),
        )
        for key, invalid_value in corruptions:
            with self.subTest(key=key):
                payload = self.complete_state().to_dict()
                payload[key] = invalid_value
                with self.assertRaises(ProjectStateError):
                    ProjectState.from_dict(payload)

        payload = self.complete_state().to_dict()
        payload["clipart"]["generation"] = []
        with self.assertRaises(ProjectStateError):
            ProjectState.from_dict(payload)

        payload = self.complete_state().to_dict()
        payload["clipart"]["prompts"][0]["references"] = "D:/ref.png"
        with self.assertRaises(ProjectStateError):
            ProjectState.from_dict(payload)

        payload = self.complete_state().to_dict()
        payload["current_step_by_mode"]["clipart"] = "files"
        with self.assertRaises(ProjectStateError):
            ProjectState.from_dict(payload)


class Version2MigrationTests(unittest.TestCase):
    def test_generate_config_migrates_without_mutating_or_copying_secrets(self):
        legacy = {
            "run_mode": "both",
            "last_work_dir": "D:/legacy",
            "retries": 4,
            "timeout": 75,
            "generation_wait_timeout": 420,
            "status_poll_interval": 15,
            "kie_upload_path": "clipart-generator-v3",
            "text_generation_model": "nano-banana-2",
            "text_generation_ratio": "3:4",
            "text_generation_resolution": "2K",
            "reference_generation_model": "gpt-image-2",
            "reference_generation_ratio": "16:9",
            "reference_generation_resolution": "4K",
            "visible_mark_cleanup_enabled": True,
            "visible_mark_cleanup_mode": "confirmed_area",
            "upscale": False,
            "upscale_provider": "local_realesrgan",
            "upscale_after": True,
            "upscale_after_provider": "kie",
            "upscale_factor": 2,
            "kie_upscale_model": "topaz/upscale-v2",
            "kie_upscale_after_model": "topaz/upscale-after",
            "local_realesrgan_profile": "photo",
            "local_realesrgan_scale": 2,
            "local_realesrgan_after_scale": 4,
            "remove_bg": True,
            "remove_bg_provider": "local_ben2",
            "kie_remove_bg_model": "recraft/remove-background-v2",
            "local_rembg_profile": "photo",
            "local_rembg_model": "birefnet-portrait",
            "local_rembg_edge_quality": "sharp",
            "local_ben2_refine_foreground": True,
            "local_ben2_alpha_threshold": 31,
            "local_ben2_edge_softness": 2,
            "local_ben2_corner_radius": 3,
            "unsharp_enabled": True,
            "unsharp_amount": 42,
            "unsharp_radius": 75,
            "unsharp_threshold": 3,
            "edge_shrink_enabled": True,
            "edge_shrink_pixels": 2,
            "trim_enabled": True,
            "trim_mode": "white",
            "cleanup_remove_xmp": True,
            "kie_api_key": "must-not-enter-project-state",
            "license_key": "must-not-enter-project-state-either",
            "unknown_future_field": {"keep": "in legacy config only"},
        }
        original = copy.deepcopy(legacy)
        state = migrate_v2_config(
            legacy,
            prompts=[{"prompt": "blue bird", "references": ["D:/bird.png"]}],
        )

        self.assertEqual(legacy, original)
        self.assertEqual(state.mode, ProjectMode.CLIPART)
        self.assertEqual(state.common.work_dir, "D:/legacy")
        self.assertEqual(state.runtime.retries, 4)
        self.assertEqual(state.runtime.timeout, 75)
        self.assertEqual(state.runtime.generation_wait_timeout, 420)
        self.assertEqual(state.runtime.status_poll_interval, 15.0)
        self.assertEqual(state.runtime.kie_upload_path, "clipart-generator-v3")
        self.assertEqual(state.clipart.generation.model, "nano-banana-2")
        self.assertEqual(state.clipart.generation.ratio, "3:4")
        self.assertEqual(state.clipart.generation.reference_model, "gpt-image-2")
        self.assertEqual(state.clipart.generation.reference_ratio, "16:9")
        self.assertEqual(state.clipart.generation.reference_resolution, "4K")
        self.assertFalse(state.clipart.operations.upscale_before)
        self.assertEqual(
            state.clipart.operations.upscale_before_provider,
            "local_realesrgan",
        )
        self.assertTrue(state.clipart.operations.upscale_after)
        self.assertEqual(state.clipart.operations.upscale_after_provider, "kie")
        self.assertEqual(state.clipart.operations.local_realesrgan_scale, 2)
        self.assertEqual(state.clipart.operations.remove_background_provider, "local_rembg")
        self.assertEqual(
            state.clipart.operations.kie_remove_bg_model,
            "recraft/remove-background",
        )
        self.assertEqual(state.clipart.operations.local_ben2_alpha_threshold, 31)
        self.assertEqual(state.clipart.operations.unsharp_radius, 75.0)
        self.assertEqual(state.clipart.operations.edge_shrink_pixels, 2)
        self.assertEqual(state.clipart.operations.trim_mode, "white")
        self.assertTrue(state.clipart.operations.remove_xmp)
        self.assertEqual(state.clipart.prompts[0].prompt, "blue bird")

        round_tripped = ProjectState.from_dict(state.to_dict())
        self.assertEqual(round_tripped.to_dict(), state.to_dict())

        serialized = json.dumps(state.to_dict(), ensure_ascii=False)
        self.assertNotIn("must-not-enter-project-state", serialized)
        self.assertNotIn("unknown_future_field", serialized)
        self.assertNotIn("kie_api_key", serialized)
        self.assertNotIn("license_key", serialized)

    def test_process_only_and_cleanup_all_are_migrated(self):
        state = migrate_v2_config(
            {
                "run_mode": "process_only",
                "cleanup_remove_all": True,
                "cleanup_preserve_icc": False,
                "cleanup_preserve_dpi": False,
            }
        )
        self.assertEqual(state.mode, ProjectMode.PROCESSING)
        self.assertEqual(state.current_step, StepId.FILES)
        self.assertTrue(state.processing.operations.remove_exif)
        self.assertTrue(state.processing.operations.remove_embedded_c2pa)
        self.assertFalse(state.processing.operations.preserve_icc)
        self.assertFalse(state.processing.operations.preserve_dpi)

    def test_non_object_legacy_config_is_rejected(self):
        with self.assertRaises(ProjectStateError):
            migrate_v2_config([])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
