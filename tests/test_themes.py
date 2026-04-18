"""Tests for tokenmap.themes module."""

from tokenmap.themes import get_theme, is_dark, get_all_theme_names, get_bg_color


class TestGetTheme:
    def test_default_green(self):
        theme = get_theme("green")
        assert theme.bg == "#ffffff"
        assert len(theme.scale) == 4

    def test_dark_theme(self):
        theme = get_theme("dark-green")
        assert theme.bg == "#0d1117"

    def test_unknown_returns_green(self):
        theme = get_theme("nonexistent")
        assert theme.bg == "#ffffff"  # same as green


class TestIsDark:
    def test_dark_themes(self):
        assert is_dark("dark-green") is True
        assert is_dark("dark-ember") is True
        assert is_dark("dark-mono") is True

    def test_light_themes(self):
        assert is_dark("green") is False
        assert is_dark("purple") is False


class TestGetAllThemeNames:
    def test_returns_10_themes(self):
        names = get_all_theme_names()
        assert len(names) == 10
        assert "green" in names
        assert "dark-green" in names


class TestGetBgColor:
    def test_known_theme(self):
        assert get_bg_color("dark-green") == "#0d1117"

    def test_unknown_returns_green_bg(self):
        assert get_bg_color("nonexistent") == "#ffffff"
