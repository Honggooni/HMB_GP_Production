"""Pixel regressions for HMB's strict metadata compositor; no live UI claims."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _hmb_image_bash_render import ImageBashRenderError, render_scene


class ImageBashRenderRegression(unittest.TestCase):
    def setUp(self):
        self.red = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        self.blue = Image.new("RGBA", (2, 2), (0, 0, 255, 255))
        self.asymmetric = Image.new("RGBA", (2, 2))
        self.asymmetric.putdata([(255, 0, 0, 255), (0, 255, 0, 255),
                                 (0, 0, 255, 255), (255, 255, 0, 255)])
        self.images = {"red": self.red, "blue": self.blue, "asymmetric": self.asymmetric}
        self.layers = [{"id": "layer-red", "source_id": "source-red", "width": 2,
                        "height": 2, "x": 1, "y": 1, "scaleX": 1, "scaleY": 1,
                        "rotation": 0, "opacity": 1, "order": 0, "type": "image"}]

    def scene(self, layers=None):
        return {"meta": {"input_images": [{"id": "source-red", "url": "red"},
                                           {"id": "source-blue", "url": "blue"}],
                         "konva_json": {"images": self.layers if layers is None else layers, "lines": []}}}

    def render(self, scene, width=2, height=2, background="#ffffff", loader=None):
        return render_scene(scene, width, height, background, loader or self.images.__getitem__)

    def test_zero_opacity_and_zero_scale_do_not_become_one(self):
        for changes in ({"opacity": 0}, {"scaleX": 0}, {"scaleY": 0}):
            with self.subTest(changes=changes):
                layer = dict(self.layers[0], **changes)
                result = self.render(self.scene([layer]))
                self.assertEqual(set(result.get_flattened_data()), {(255, 255, 255, 255)})

    def test_none_defaults_remain_distinct_from_zero(self):
        layer = dict(self.layers[0], opacity=None, scaleX=None, scaleY=None, visible=None)
        self.assertEqual(self.render(self.scene([layer])).tobytes(), self.red.tobytes())

    def test_alpha_source_over_preserves_opaque_background(self):
        self.images["red"] = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
        result = self.render(self.scene(), background="#0000ff")
        self.assertEqual(set(result.get_flattened_data()), {(128, 0, 127, 255)})

    def test_opacity_combines_once_with_source_alpha(self):
        self.images["red"] = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
        result = self.render(self.scene([dict(self.layers[0], opacity=0.5)]), background="#0000ff")
        self.assertEqual(set(result.get_flattened_data()), {(64, 0, 191, 255)})

    def test_asymmetric_mirrors_keep_dimensions_and_center(self):
        original = list(self.asymmetric.get_flattened_data())
        expected = {(-1, 1): [original[1], original[0], original[3], original[2]],
                    (1, -1): [original[2], original[3], original[0], original[1]],
                    (-1, -1): [original[3], original[2], original[1], original[0]]}
        for (sx, sy), pixels in expected.items():
            with self.subTest(scale=(sx, sy)):
                layer = dict(self.layers[0], source_id=None, src="asymmetric", scaleX=sx, scaleY=sy)
                self.assertEqual(list(self.render(self.scene([layer])).get_flattened_data()), pixels)

    def test_clockwise_quarter_turn_uses_center_pivot(self):
        layer = dict(self.layers[0], source_id=None, src="asymmetric", rotation=90)
        source = list(self.asymmetric.get_flattened_data())
        self.assertEqual(list(self.render(self.scene([layer])).get_flattened_data()),
                         [source[2], source[0], source[3], source[1]])

    def test_flipped_rotated_non_square_layer_and_offset_position(self):
        image = Image.new("RGBA", (3, 2))
        colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
                  (255, 255, 0, 255), (0, 255, 255, 255), (255, 0, 255, 255)]
        image.putdata(colors)
        self.images["rect"] = image
        layer = dict(self.layers[0], source_id=None, src="rect", width=3, height=2,
                     scaleX=-1, rotation=90, x=3, y=2.5)
        result = self.render(self.scene([layer]), width=6, height=5, background="transparent")
        # Flip horizontally, then rotate clockwise: rows [F,C], [E,B], [D,A].
        self.assertEqual([result.getpixel((x, y)) for y in range(1, 4) for x in range(2, 4)],
                         [colors[5], colors[2], colors[4], colors[1], colors[3], colors[0]])
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))

    def test_source_reordering_does_not_transfer_layer_settings(self):
        layer = dict(self.layers[0], opacity=0.25)
        scene = self.scene([layer])
        before = self.render(scene)
        scene["meta"]["input_images"].reverse()
        self.assertEqual(before.tobytes(), self.render(scene).tobytes())
        self.assertEqual(before.getpixel((0, 0)), (255, 191, 191, 255))

    def test_duplicate_layers_and_explicit_order_are_preserved(self):
        layers = [dict(self.layers[0], id="copy-2", x=3, order=20),
                  dict(self.layers[0], id="copy-1", order=0),
                  dict(self.layers[0], id="blue-top", source_id="source-blue", order=10)]
        result = self.render(self.scene(layers), width=4)
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(result.getpixel((3, 0)), (255, 0, 0, 255))

    def test_brush_raster_resolves_by_layer_identity(self):
        scene = self.scene([dict(self.layers[0], id="brush-1", source_id=None, type="brush")])
        scene["meta"]["input_images"].append({"id": "brush-1", "url": "blue"})
        self.assertEqual(self.render(scene).tobytes(), self.blue.tobytes())

    def test_hidden_layer_need_not_load(self):
        layer = dict(self.layers[0], source_id=None, src="missing", visible=False)
        self.assertEqual(self.render(self.scene([layer])).getpixel((0, 0)), (255, 255, 255, 255))

    def test_failed_required_layer_aborts_without_a_partial_return(self):
        scene = self.scene([self.layers[0], dict(self.layers[0], id="missing-layer", source_id=None,
                                               src="missing", order=1)])
        received = []
        with self.assertRaisesRegex(ImageBashRenderError, "could not be loaded"):
            received.append(self.render(scene))
        self.assertEqual(received, [])

    def test_missing_source_aborts_instead_of_silent_skip(self):
        with self.assertRaisesRegex(ImageBashRenderError, "no image source"):
            self.render(self.scene([dict(self.layers[0], source_id="unknown")]))

    def test_conflicting_source_identity_aborts(self):
        scene = self.scene()
        scene["meta"]["input_images"].append({"id": "source-red", "url": "blue"})
        with self.assertRaisesRegex(ImageBashRenderError, "different images"):
            self.render(scene)

    def test_raw_lines_fail_instead_of_silently_disappearing(self):
        scene = self.scene()
        scene["meta"]["konva_json"]["lines"] = [{"points": [0, 0, 1, 1]}]
        with self.assertRaisesRegex(ImageBashRenderError, "Apply render"):
            self.render(scene)

    def test_scene_and_loader_images_are_not_mutated(self):
        scene = self.scene([dict(self.layers[0], opacity=0.2)])
        before = copy.deepcopy(scene)
        pixels = self.red.tobytes()
        self.render(scene)
        self.assertEqual(scene, before)
        self.assertEqual(self.red.tobytes(), pixels)

    def test_clipping_and_transparent_background(self):
        result = self.render(self.scene([dict(self.layers[0], x=0, y=0)]), background="#00000000")
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(result.getpixel((1, 1)), (0, 0, 0, 0))

    def test_malformed_numbers_cannot_emit_an_image(self):
        for changes in ({"scaleX": float("nan")}, {"rotation": float("inf")},
                        {"opacity": -1}, {"opacity": 1.1}, {"width": -2}):
            with self.subTest(changes=changes), self.assertRaises(ImageBashRenderError):
                self.render(self.scene([dict(self.layers[0], **changes)]))

    def test_unsupported_raw_blend_and_skew_fail_explicitly(self):
        for changes in ({"globalCompositeOperation": "destination-out"}, {"skewX": 0.2}):
            with self.subTest(changes=changes), self.assertRaises(ImageBashRenderError):
                self.render(self.scene([dict(self.layers[0], **changes)]))

    def test_canvas_dimensions_reject_invalid_zero_values(self):
        for width, height in ((0, 2), (2, 0), (-1, 2), (True, 2), (2.0, 2)):
            with self.subTest(dimensions=(width, height)), self.assertRaises(ImageBashRenderError):
                self.render(self.scene(), width=width, height=height)


if __name__ == "__main__":
    unittest.main(verbosity=2)
