"""Guards for the report's proportional type scale + structural cleanup.

Keeps the report on one type ladder: every font-size must reference a --fs-* token (no raw px,
so nothing can drift below the 11px floor), the scale must be defined, and the retired left
sidebar's CSS must stay gone.
"""
import re

from mlbmodel.report.app import _SHELL_CSS
from mlbmodel.report.matchup import _CSS

_SCALE_TOKENS = (
    "--fs-2xs", "--fs-xs", "--fs-sm", "--fs-md",
    "--fs-lg", "--fs-xl", "--fs-2xl", "--fs-3xl",
)


def test_type_scale_tokens_defined():
    for token in _SCALE_TOKENS:
        assert f"{token}:" in _CSS, f"type-scale token {token} not defined"


def test_no_hardcoded_font_sizes():
    for name, css in (("_CSS", _CSS), ("_SHELL_CSS", _SHELL_CSS)):
        raw = re.findall(r"font-size:(\d+\.?\d*)px", css)
        raw += [match[1] for match in re.findall(r"(font:\s*\d+\s+)(\d+\.?\d*)px", css)]
        assert not raw, f"{name} has hard-coded font-size px (use --fs-* tokens): {raw}"


def test_no_dead_sidebar_css():
    for dead in ("#appshell", "#nav{", ".navb{"):
        assert dead not in _SHELL_CSS, f"dead sidebar selector {dead!r} still present"
