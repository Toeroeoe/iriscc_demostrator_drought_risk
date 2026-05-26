"""Tests for ThemeConfig — theme management for Shiny app and matplotlib.

These tests cover the pure-Python logic in theme_config.py:
colour extraction, font helpers, the matplotlib integration, and
the factory function. They do not require a running Shiny server or
any geospatial data files.
"""

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — must come before other mpl imports

import matplotlib as mpl
import pytest

from src.shiny_app.theme_config import (
    GOOGLE_FONTS_URL,
    ThemeConfig,
    get_theme_config,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dark_theme():
    return ThemeConfig("dark")


@pytest.fixture
def light_theme():
    return ThemeConfig("light")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_dark_mode_stored(self, dark_theme):
        assert dark_theme.mode == "dark"

    def test_light_mode_stored(self, light_theme):
        assert light_theme.mode == "light"

    def test_default_is_light(self):
        assert ThemeConfig().mode == "light"


# ---------------------------------------------------------------------------
# Colour dictionary
# ---------------------------------------------------------------------------

_REQUIRED_COLOR_KEYS = {
    "primary",
    "secondary",
    "text",
    "background",
    "border",
    "success",
    "danger",
    "warning",
    "info",
}


class TestColors:
    def test_dark_has_all_color_keys(self, dark_theme):
        assert _REQUIRED_COLOR_KEYS.issubset(dark_theme.colors)

    def test_light_has_all_color_keys(self, light_theme):
        assert _REQUIRED_COLOR_KEYS.issubset(light_theme.colors)

    def test_all_colors_are_hex_strings(self, dark_theme):
        for key, value in dark_theme.colors.items():
            assert isinstance(value, str), f"Color '{key}' is not a string"
            assert value.startswith("#"), f"Color '{key}' does not start with '#'"

    def test_dark_and_light_backgrounds_differ(self, dark_theme, light_theme):
        assert dark_theme.colors["background"] != light_theme.colors["background"]


# ---------------------------------------------------------------------------
# Font configuration
# ---------------------------------------------------------------------------


class TestFonts:
    def test_fonts_dict_has_three_keys(self, dark_theme):
        assert set(dark_theme.fonts) == {"body", "heading", "mono"}

    def test_font_sizes_has_required_keys(self, dark_theme):
        assert {"small", "base", "large", "title", "heading"}.issubset(
            dark_theme.font_sizes
        )

    def test_font_sizes_are_positive_numbers(self, dark_theme):
        for key, size in dark_theme.font_sizes.items():
            assert isinstance(size, (int, float)), f"font_sizes['{key}'] is not numeric"
            assert size > 0, f"font_sizes['{key}'] is not positive"


# ---------------------------------------------------------------------------
# get_font_family
# ---------------------------------------------------------------------------


class TestGetFontFamily:
    def test_body_returns_list(self, dark_theme):
        assert isinstance(dark_theme.get_font_family("body"), list)

    def test_body_includes_inter(self, dark_theme):
        assert "Inter" in dark_theme.get_font_family("body")

    def test_heading_includes_crimson_text(self, dark_theme):
        assert "Crimson Text" in dark_theme.get_font_family("heading")

    def test_mono_includes_ibm_plex_mono(self, dark_theme):
        assert "IBM Plex Mono" in dark_theme.get_font_family("mono")

    def test_all_variants_return_non_empty_list(self, dark_theme):
        for variant in ("body", "heading", "mono"):
            result = dark_theme.get_font_family(variant)
            assert isinstance(result, list) and len(result) > 0, (
                f"get_font_family('{variant}') returned an empty list"
            )


# ---------------------------------------------------------------------------
# get_plot_palette
# ---------------------------------------------------------------------------

_REQUIRED_PALETTE_KEYS = {"background", "text", "grid", "primary", "accent"}


class TestGetPlotPalette:
    def test_dark_palette_has_required_keys(self, dark_theme):
        assert _REQUIRED_PALETTE_KEYS.issubset(dark_theme.get_plot_palette())

    def test_light_palette_has_required_keys(self, light_theme):
        assert _REQUIRED_PALETTE_KEYS.issubset(light_theme.get_plot_palette())

    def test_palette_values_are_strings(self, dark_theme):
        for key, val in dark_theme.get_plot_palette().items():
            assert isinstance(val, str), f"Palette key '{key}' is not a string"


# ---------------------------------------------------------------------------
# apply_to_matplotlib
# ---------------------------------------------------------------------------


class TestApplyToMatplotlib:
    def test_does_not_raise(self, dark_theme):
        dark_theme.apply_to_matplotlib()  # must not throw

    def test_sets_figure_facecolor(self, dark_theme):
        dark_theme.apply_to_matplotlib()
        assert mpl.rcParams["figure.facecolor"] == dark_theme.colors["background"]

    def test_sets_axes_facecolor(self, dark_theme):
        dark_theme.apply_to_matplotlib()
        assert mpl.rcParams["axes.facecolor"] == dark_theme.colors["background"]

    def test_sets_font_size(self, dark_theme):
        dark_theme.apply_to_matplotlib()
        assert mpl.rcParams["font.size"] == dark_theme.font_sizes["base"]


# ---------------------------------------------------------------------------
# get_font_usage_guide
# ---------------------------------------------------------------------------


class TestGetFontUsageGuide:
    def test_returns_three_sections(self, dark_theme):
        assert set(dark_theme.get_font_usage_guide()) == {"body", "heading", "mono"}

    def test_each_section_has_required_fields(self, dark_theme):
        guide = dark_theme.get_font_usage_guide()
        for section_name, section in guide.items():
            for field in ("font", "usage"):
                assert field in section, (
                    f"Section '{section_name}' is missing field '{field}'"
                )


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr_is_string(self, dark_theme):
        assert isinstance(repr(dark_theme), str)

    def test_repr_contains_mode(self, dark_theme):
        assert "dark" in repr(dark_theme)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestGetThemeConfig:
    def test_returns_theme_config_instance(self):
        assert isinstance(get_theme_config("dark"), ThemeConfig)

    def test_dark_mode(self):
        assert get_theme_config("dark").mode == "dark"

    def test_light_mode(self):
        assert get_theme_config("light").mode == "light"


# ---------------------------------------------------------------------------
# GOOGLE_FONTS_URL constant
# ---------------------------------------------------------------------------


class TestGoogleFontsUrl:
    def test_is_string(self):
        assert isinstance(GOOGLE_FONTS_URL, str)

    def test_starts_with_https(self):
        assert GOOGLE_FONTS_URL.startswith("https://")

    def test_includes_inter(self):
        assert "Inter" in GOOGLE_FONTS_URL

    def test_includes_crimson_text(self):
        assert "Crimson" in GOOGLE_FONTS_URL

    def test_includes_ibm_plex_mono(self):
        assert "IBM+Plex+Mono" in GOOGLE_FONTS_URL
