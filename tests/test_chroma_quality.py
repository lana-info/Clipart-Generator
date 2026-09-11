import unittest

from PIL import Image, ImageFilter

from chroma_quality import (
    geometry_topology_quality,
    measure_alpha_profile,
    reference_quality,
)


class ReferenceQualityTests(unittest.TestCase):
    def test_single_bright_error_is_not_hidden_by_canvas_average(self):
        truth = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        truth.putpixel((50, 50), (40, 40, 40, 128))
        actual = truth.copy()
        actual.putpixel((50, 50), (255, 40, 40, 128))
        report = reference_quality(actual, truth)
        edge = report["regions"]["partial"]["rgb_max_channel"]
        self.assertEqual(edge["count"], 1)
        self.assertAlmostEqual(edge["max"], 215 / 255, places=6)
        for bg in report["composites"].values():
            self.assertAlmostEqual(bg["partial"]["max"], 215 * 128 / 255**2, places=6)

    def test_transparent_rgb_does_not_count_as_visible_damage(self):
        truth = Image.new("RGBA", (2, 2), (255, 0, 255, 0))
        actual = Image.new("RGBA", (2, 2), (0, 255, 0, 0))
        report = reference_quality(actual, truth)
        self.assertNotIn("rgb_max_channel", report["regions"]["background"])
        self.assertIsNone(report["regions"]["partial"]["alpha"]["max"])
        for bg in report["composites"].values():
            self.assertEqual(bg["background"]["max"], 0)

    def test_alpha_error_is_measured_inside_opaque_subject(self):
        truth = Image.new("RGBA", (1, 1), (120, 80, 180, 255))
        actual = Image.new("RGBA", (1, 1), (120, 80, 180, 184))
        self.assertAlmostEqual(reference_quality(actual, truth)["regions"]["opaque"]["alpha"]["max"], 71 / 255, places=6)

    def test_dimensions_are_checked(self):
        with self.assertRaises(ValueError):
            reference_quality(Image.new("RGBA", (1, 1)), Image.new("RGBA", (2, 1)))


class GeometryTopologyQualityTests(unittest.TestCase):
    @staticmethod
    def _opaque_box(size=(24, 24), box=(7, 7, 17, 17)):
        image = Image.new("RGBA", size)
        for y in range(box[1], box[3]):
            for x in range(box[0], box[2]):
                image.putpixel((x, y), (30, 80, 140, 255))
        return image

    def test_perfect_mask_has_matching_components_and_zero_boundary_distance(self):
        truth = self._opaque_box()
        report = geometry_topology_quality(truth.copy(), truth)

        self.assertEqual(report["components"]["reference"]["count"], 1)
        self.assertEqual(report["components"]["actual"]["count"], 1)
        self.assertEqual(report["components"]["overlap"]["lost_reference_count"], 0)
        self.assertEqual(report["holes"]["overlap"]["lost_reference_count"], 0)
        self.assertEqual(
            report["boundary_distance"]["reference_to_actual"]["pixels"]["max"], 0
        )
        self.assertEqual(
            report["boundary_distance"]["actual_to_reference"]["pixels"]["max"], 0
        )

    def test_broad_alpha_blur_is_visible_as_boundary_displacement(self):
        truth = self._opaque_box()
        actual = truth.filter(ImageFilter.GaussianBlur(radius=3))
        report = geometry_topology_quality(actual, truth)

        self.assertGreater(
            report["boundary_distance"]["actual_to_reference"]["pixels"]["max"], 1.0
        )
        self.assertLess(report["support"]["iou"], 1.0)

    def test_tiny_low_alpha_component_is_support_and_its_loss_is_reported_by_overlap(self):
        truth = self._opaque_box()
        # A single 8-bit alpha unit is valid subpixel coverage, not absence.
        truth.putpixel((2, 2), (255, 255, 255, 1))
        preserved = geometry_topology_quality(truth.copy(), truth)
        self.assertEqual(preserved["components"]["reference"]["count"], 2)
        self.assertEqual(preserved["components"]["overlap"]["lost_reference_count"], 0)

        actual = truth.copy()
        actual.putpixel((2, 2), (255, 255, 255, 0))
        report = geometry_topology_quality(actual, truth)
        self.assertEqual(report["components"]["reference"]["count"], 2)
        self.assertEqual(report["components"]["actual"]["count"], 1)
        self.assertEqual(report["components"]["overlap"]["lost_reference_count"], 1)
        self.assertLess(report["support"]["reference_recall"], 1.0)

    def test_moved_hole_is_lost_even_when_component_and_hole_counts_match(self):
        truth = self._opaque_box(size=(26, 26), box=(3, 3, 23, 23))
        actual = truth.copy()
        for y in range(7, 10):
            for x in range(7, 10):
                truth.putpixel((x, y), (0, 0, 0, 0))
        for y in range(15, 18):
            for x in range(15, 18):
                actual.putpixel((x, y), (0, 0, 0, 0))

        report = geometry_topology_quality(actual, truth)
        self.assertEqual(report["components"]["reference"]["count"], 1)
        self.assertEqual(report["components"]["actual"]["count"], 1)
        self.assertEqual(report["holes"]["reference"]["count"], 1)
        self.assertEqual(report["holes"]["actual"]["count"], 1)
        self.assertEqual(report["holes"]["overlap"]["lost_reference_count"], 1)
        self.assertEqual(report["holes"]["overlap"]["unmatched_actual_count"], 1)

    def test_foreground_and_holes_use_explicit_dual_connectivity(self):
        image = Image.new("RGBA", (5, 5))
        # An 8-connected foreground ring with a diagonal background escape.
        for y in range(1, 4):
            for x in range(1, 4):
                if (x, y) not in {(1, 1), (2, 2)}:
                    image.putpixel((x, y), (1, 1, 1, 255))
        report = geometry_topology_quality(image, image)
        self.assertEqual(report["connectivity"], {"foreground_components": 8, "background_holes": 4})
        self.assertEqual(report["components"]["reference"]["count"], 1)
        self.assertEqual(report["holes"]["reference"]["count"], 1)

    def test_dense_holes_stop_at_configured_region_limit(self):
        image = self._opaque_box(size=(20, 20), box=(1, 1, 19, 19))
        # Isolated transparent pixels are distinct 4-connected holes.
        for y in range(3, 18, 3):
            for x in range(3, 18, 3):
                image.putpixel((x, y), (0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, "Hole count exceeds max_regions"):
            geometry_topology_quality(image, image, max_regions=8)

    def test_dimensions_source_immutability_and_empty_evidence_are_explicit(self):
        truth = Image.new("RGBA", (5, 5))
        actual = Image.new("RGBA", (5, 5))
        before_actual = actual.tobytes()
        before_truth = truth.tobytes()
        report = geometry_topology_quality(actual, truth)
        self.assertEqual(actual.tobytes(), before_actual)
        self.assertEqual(truth.tobytes(), before_truth)
        self.assertFalse(report["boundary_distance"]["reference_to_actual"]["evidence"])
        self.assertIsNone(report["boundary_distance"]["reference_to_actual"]["pixels"]["max"])
        with self.assertRaises(ValueError):
            geometry_topology_quality(actual, Image.new("RGBA", (4, 5)))
        with self.assertRaises(ValueError):
            geometry_topology_quality(actual, truth, max_pixels=24)


class AlphaProfileTests(unittest.TestCase):
    def test_monotonic_profile_uses_interpolated_05_to_95_crossings(self):
        report = measure_alpha_profile((0.0, 0.25, 0.75, 1.0), spacing=0.5)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["direction"], "increasing")
        self.assertAlmostEqual(report["crossing_05_pixels"], 0.1)
        self.assertAlmostEqual(report["crossing_95_pixels"], 1.4)
        self.assertAlmostEqual(report["width_05_95_pixels"], 1.3)

    def test_nonmonotonic_profile_is_ambiguous_not_an_aa_measurement(self):
        report = measure_alpha_profile((0.0, 0.5, 0.25, 1.0))
        self.assertEqual(report["status"], "ambiguous")
        self.assertIsNone(report["width_05_95_pixels"])

    def test_profile_without_both_crossings_has_no_evidence(self):
        report = measure_alpha_profile((0.1, 0.3, 0.7))
        self.assertEqual(report["status"], "no_evidence")
        self.assertIsNone(report["crossing_05_pixels"])

    def test_profile_generator_stops_at_configured_sample_limit(self):
        with self.assertRaisesRegex(ValueError, "Profile sample count exceeds max_samples"):
            measure_alpha_profile((0.5 for _ in range(10)), max_samples=3)
