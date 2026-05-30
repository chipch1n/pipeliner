import numpy as np
from PIL import Image
import pytest

from backend.app.nodes.base import BaseNode
from backend.app.nodes.blur import BlurNode
from backend.app.nodes.noise import NoiseNode
from backend.app.nodes.make_mask import MakeMaskNode
from backend.app.nodes.hf_image_to_image import HfImageToImageNode
from backend.app.nodes.factory import create_node, NODE_REGISTRY

@pytest.fixture
def gradient_image():
    img = Image.new("RGB", (100, 100), color="white")
    for x in range(100):
        for y in range(100):
            r = int(255 * (x / 99))
            g = 0
            b = int(255 * (y / 99))
            img.putpixel((x, y), (r, g, b))
    return img

@pytest.fixture
def solid_red_image():
    return Image.new("RGB", (50, 50), color=(255, 0, 0))

@pytest.fixture
def solid_gray_image():
    return Image.new("RGB", (50, 50), color=(128, 128, 128))

@pytest.fixture
def checkerboard_image():
    img = Image.new("L", (100, 100), color=0)
    for x in range(100):
        for y in range(100):
            if (x // 10 + y // 10) % 2 == 0:
                img.putpixel((x, y), 255)
    return img

class TestBaseNode:
    def test_base_node_is_abstract(self):
        with pytest.raises(TypeError):
            BaseNode(params={"test": True})

    def test_base_node_requires_apply(self):
        class IncompleteNode(BaseNode):
            pass

        with pytest.raises(TypeError):
            IncompleteNode()

    def test_minimal_subclass(self):
        class MinimalNode(BaseNode):
            def apply(self, image: Image.Image) -> Image.Image:
                return image

        node = MinimalNode({"key": "value"})
        assert node.params == {"key": "value"}

        img = Image.new("RGB", (10, 10))
        result = node.apply(img)
        assert np.array_equal(np.array(result), np.array(img))

    def test_default_params(self):
        class MinimalNode(BaseNode):
            def apply(self, image: Image.Image) -> Image.Image:
                return image

        assert MinimalNode().params == {}
        assert MinimalNode(None).params == {}
        assert MinimalNode({"radius": 5}).params == {"radius": 5}

    def test_params_are_accessible(self, gradient_image):
        class ParamCheckingNode(BaseNode):
            def apply(self, image: Image.Image) -> Image.Image:
                factor = self.params.get("factor", 1)
                return image.resize((
                    int(image.width * factor),
                    int(image.height * factor)
                ))

        node = ParamCheckingNode({"factor": 2})
        result = node.apply(gradient_image)
        assert result.size == (200, 200)

class TestBlurNode:
    def test_default_blur(self, gradient_image):
        node = BlurNode()
        result = node.apply(gradient_image)

        assert isinstance(result, Image.Image)
        assert result.size == gradient_image.size
        assert result.mode == "RGB"

    def test_blur_reduces_variance(self, gradient_image):
        node = BlurNode({"radius": 5})
        result = node.apply(gradient_image)

        original_arr = np.array(gradient_image)
        result_arr = np.array(result)

        original_diff = np.abs(np.diff(original_arr, axis=0)).mean()
        result_diff = np.abs(np.diff(result_arr, axis=0)).mean()

        assert result_diff < original_diff

    def test_blur_radius_increases_effect(self, gradient_image):
        result_small = BlurNode({"radius": 2}).apply(gradient_image.copy())
        result_large = BlurNode({"radius": 20}).apply(gradient_image.copy())

        arr_original = np.array(gradient_image)
        arr_small = np.array(result_small)
        arr_large = np.array(result_large)

        diff_small = np.abs(arr_small - arr_original).mean()
        diff_large = np.abs(arr_large - arr_original).mean()

        assert diff_large > diff_small

    def test_blur_max_radius(self, gradient_image):
        node = BlurNode({"radius": 50})
        result = node.apply(gradient_image)

        arr = np.array(result)
        std_per_channel = arr.std(axis=(0, 1))
        assert all(s < 80 for s in std_per_channel)

    def test_blur_on_solid_color(self, solid_red_image):
        node = BlurNode({"radius": 20})
        result = node.apply(solid_red_image)

        arr_original = np.array(solid_red_image)
        arr_result = np.array(result)

        assert np.allclose(arr_original, arr_result, atol=5)

    def test_blur_zero_radius(self, gradient_image):
        node = BlurNode({"radius": 0})
        result = node.apply(gradient_image)

        arr_original = np.array(gradient_image)
        arr_result = np.array(result)

        assert np.allclose(arr_original, arr_result, atol=7)

    def test_blur_preserves_overall_brightness(self, gradient_image):
        node = BlurNode({"radius": 15})
        result = node.apply(gradient_image)

        original_mean = np.array(gradient_image).mean()
        result_mean = np.array(result).mean()

        assert abs(original_mean - result_mean) / original_mean < 0.05

class TestNoiseNode:
    def test_default_noise(self, gradient_image):
        node = NoiseNode()
        result = node.apply(gradient_image)

        assert isinstance(result, Image.Image)
        assert result.size == gradient_image.size
        assert result.mode == "RGB"

    def test_noise_increases_variance(self, solid_gray_image):
        node = NoiseNode({"intensity": 30, "seed": 42})
        result = node.apply(solid_gray_image)

        original_std = np.array(solid_gray_image).std()
        result_std = np.array(result).std()

        assert result_std > original_std

    def test_noise_zero_intensity(self, gradient_image):
        node = NoiseNode({"intensity": 0, "seed": 42})
        result = node.apply(gradient_image)

        assert np.array_equal(np.array(result), np.array(gradient_image))

    def test_noise_seed_reproducibility(self, gradient_image):
        node1 = NoiseNode({"intensity": 25, "seed": 42})
        node2 = NoiseNode({"intensity": 25, "seed": 42})

        result1 = node1.apply(gradient_image.copy())
        result2 = node2.apply(gradient_image.copy())

        assert np.array_equal(np.array(result1), np.array(result2))

    def test_noise_different_seeds_different(self, gradient_image):
        node1 = NoiseNode({"intensity": 25, "seed": 42})
        node2 = NoiseNode({"intensity": 25, "seed": 43})

        result1 = node1.apply(gradient_image.copy())
        result2 = node2.apply(gradient_image.copy())

        assert not np.array_equal(np.array(result1), np.array(result2))

    def test_noise_intensity_scales_effect(self, solid_gray_image):
        result_low = NoiseNode({"intensity": 10, "seed": 42}).apply(solid_gray_image.copy())
        result_high = NoiseNode({"intensity": 50, "seed": 42}).apply(solid_gray_image.copy())

        std_low = np.array(result_low).std()
        std_high = np.array(result_high).std()

        assert std_high > std_low

    def test_noise_values_in_valid_range(self, gradient_image):
        node = NoiseNode({"intensity": 100, "seed": 99})
        result = node.apply(gradient_image)

        arr = np.array(result)
        assert arr.min() >= 0
        assert arr.max() <= 255

    def test_noise_preserves_overall_brightness(self, solid_gray_image):
        node = NoiseNode({"intensity": 50, "seed": 42})
        result = node.apply(solid_gray_image)

        original_mean = np.array(solid_gray_image).mean()
        result_mean = np.array(result).mean()

        assert abs(original_mean - result_mean) / max(original_mean, 1) < 0.05

    def test_noise_on_black_image(self):
        black_img = Image.new("RGB", (50, 50), color=(0, 0, 0))
        node = NoiseNode({"intensity": 50, "seed": 42})
        result = node.apply(black_img)

        arr = np.array(result)
        assert arr.min() >= 0

class TestMakeMaskNode:
    def test_default_mask(self, gradient_image):
        node = MakeMaskNode()
        result = node.apply(gradient_image)

        assert result.mode == "L"
        assert result.size == gradient_image.size

    def test_mask_binary_output(self, checkerboard_image):
        node = MakeMaskNode({"threshold": 128})
        result = node.apply(checkerboard_image)

        arr = np.array(result)
        unique_values = set(np.unique(arr))
        assert unique_values <= {0, 255}

    def test_mask_threshold_behavior(self, solid_gray_image):
        node1 = MakeMaskNode({"threshold": 128})
        result1 = node1.apply(solid_gray_image)
        arr1 = np.array(result1)
        assert np.all(arr1 == 255)

        node2 = MakeMaskNode({"threshold": 129})
        result2 = node2.apply(solid_gray_image)
        arr2 = np.array(result2)
        assert np.all(arr2 == 0)

    def test_mask_invert_complement(self, checkerboard_image):
        node_normal = MakeMaskNode({"threshold": 128, "invert": False})
        node_inverted = MakeMaskNode({"threshold": 128, "invert": True})

        result_normal = node_normal.apply(checkerboard_image.copy())
        result_inverted = node_inverted.apply(checkerboard_image.copy())

        arr_normal = np.array(result_normal)
        arr_inverted = np.array(result_inverted)

        assert np.array_equal(255 - arr_normal, arr_inverted)

    def test_mask_threshold_zero(self, gradient_image):
        node = MakeMaskNode({"threshold": 0})
        result = node.apply(gradient_image)

        arr = np.array(result)
        assert np.all(arr == 255)

    def test_mask_threshold_max(self, gradient_image):
        node = MakeMaskNode({"threshold": 255})
        result = node.apply(gradient_image)

        arr = np.array(result)
        assert np.mean(arr) < 5

    def test_mask_low_threshold_more_white(self, gradient_image):
        result_high_threshold = MakeMaskNode({"threshold": 200}).apply(gradient_image.copy())
        result_low_threshold = MakeMaskNode({"threshold": 50}).apply(gradient_image.copy())

        mean_high = np.array(result_high_threshold).mean()
        mean_low = np.array(result_low_threshold).mean()

        assert mean_low > mean_high

    def test_mask_preserves_size(self, gradient_image):
        node = MakeMaskNode({"threshold": 128})
        result = node.apply(gradient_image)

        assert result.size == gradient_image.size

class TestNodeFactory:
    def test_create_blur_node(self):
        node = create_node("blur", {"radius": 5})
        assert isinstance(node, BlurNode)
        assert node.params == {"radius": 5}

    def test_create_noise_node(self):
        node = create_node("noise", {"intensity": 30})
        assert isinstance(node, NoiseNode)
        assert node.params == {"intensity": 30}

    def test_create_make_mask_node(self):
        node = create_node("make_mask", {"threshold": 200})
        assert isinstance(node, MakeMaskNode)
        assert node.params == {"threshold": 200}

    def test_unsupported_node_type(self):
        with pytest.raises(ValueError) as exc_info:
            create_node("invalid_type", {})
        assert "Unsupported node type" in str(exc_info.value)

    def test_case_sensitive_node_types(self):
        with pytest.raises(ValueError):
            create_node("Blur", {})

    def test_create_hf_image_to_image_node(self):
        node = create_node("hf_image_to_image", {"model": "timbrooks/instruct-pix2pix"})
        assert isinstance(node, HfImageToImageNode)
        assert node.params["model"] == "timbrooks/instruct-pix2pix"

    def test_registry_completeness(self):
        assert NODE_REGISTRY == {
            "blur": BlurNode,
            "noise": NoiseNode,
            "make_mask": MakeMaskNode,
            "hf_image_to_image": HfImageToImageNode,
        }

    def test_factory_nodes_are_functional(self, gradient_image):
        blur = create_node("blur", {"radius": 3})
        result = blur.apply(gradient_image.copy())
        assert isinstance(result, Image.Image)

        noise = create_node("noise", {"intensity": 10, "seed": 42})
        result = noise.apply(gradient_image.copy())
        assert isinstance(result, Image.Image)

        mask = create_node("make_mask", {"threshold": 128})
        result = mask.apply(gradient_image.copy())
        assert result.mode == "L"

class TestNodePipeline:
    def test_blur_then_noise_pipeline(self, gradient_image):
        blurred = create_node("blur", {"radius": 5}).apply(gradient_image)
        noisy = create_node("noise", {"intensity": 15, "seed": 42}).apply(blurred)

        assert isinstance(noisy, Image.Image)
        assert noisy.size == gradient_image.size

        assert not np.array_equal(np.array(noisy), np.array(gradient_image))
        assert not np.array_equal(np.array(noisy), np.array(blurred))

    def test_noise_then_mask_pipeline(self, gradient_image):
        noisy = create_node("noise", {"intensity": 20, "seed": 42}).apply(gradient_image.copy())
        mask = create_node("make_mask", {"threshold": 128}).apply(noisy)

        assert mask.mode == "L"

        arr = np.array(mask)
        assert set(np.unique(arr)) <= {0, 255}

    def test_deterministic_pipeline(self, gradient_image):
        def run_pipeline(img):
            img = create_node("blur", {"radius": 5}).apply(img)
            img = create_node("noise", {"intensity": 10, "seed": 42}).apply(img)
            return img

        result1 = run_pipeline(gradient_image.copy())
        result2 = run_pipeline(gradient_image.copy())

        assert np.array_equal(np.array(result1), np.array(result2))

    def test_different_seeds_different_output(self, gradient_image):
        def run_pipeline(img, seed):
            img = create_node("blur", {"radius": 3}).apply(img)
            img = create_node("noise", {"intensity": 10, "seed": seed}).apply(img)
            return img

        result1 = run_pipeline(gradient_image.copy(), 10)
        result2 = run_pipeline(gradient_image.copy(), 20)

        assert not np.array_equal(np.array(result1), np.array(result2))

    def test_multiple_blurs_increase_effect(self, gradient_image):
        single_blur = BlurNode({"radius": 5}).apply(gradient_image.copy())

        double_blur = gradient_image.copy()
        double_blur = BlurNode({"radius": 5}).apply(double_blur)
        double_blur = BlurNode({"radius": 5}).apply(double_blur)

        single_arr = np.array(single_blur)
        double_arr = np.array(double_blur)

        single_diff = np.abs(np.diff(single_arr, axis=0)).mean()
        double_diff = np.abs(np.diff(double_arr, axis=0)).mean()

        assert double_diff < single_diff