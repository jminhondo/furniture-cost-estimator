"""
Name-based component classifier.

Matches component names against FURNITURE_TAXONOMY keyword patterns.
Returns (TipoInferido, confidence) or None if no match.
"""
import re

from src.models.project import TipoInferido

# Word-separator pattern used to build token-aware matches.
# In SketchUp component names, words are separated by underscores, spaces,
# hyphens, dots or digits — NOT by \b (which treats _ as a word char).
_SEP = r"(?:^|(?<=[_\s\-\./\d]))"   # start of token
_END = r"(?=[_\s\-\./\d]|$)"        # end of token


def _w(keyword: str) -> str:
    """Wrap a keyword with token-boundary lookarounds."""
    return _SEP + keyword + _END


# Patterns are applied case-insensitively. First match wins.
# More specific compound types (cajon_*) come before their root words.
FURNITURE_TAXONOMY: dict[TipoInferido, list[str]] = {
    # Cajón sub-types — must precede generic "fondo" / "lateral" etc.
    TipoInferido.cajon_frente: [
        r"caj[oó]n[_\s-]*frente",
        r"frente[_\s-]*caj[oó]n",
        r"drawer[_\s-]*front",
        r"front[_\s-]*drawer",
    ],
    TipoInferido.cajon_lateral: [
        r"caj[oó]n[_\s-]*lat",
        r"lat[_\s-]*caj[oó]n",
        r"drawer[_\s-]*side",
        r"side[_\s-]*drawer",
    ],
    TipoInferido.cajon_fondo: [
        r"caj[oó]n[_\s-]*fondo",
        r"fondo[_\s-]*caj[oó]n",
        r"drawer[_\s-]*back",
        r"back[_\s-]*drawer",
    ],
    TipoInferido.puerta: [
        _w("puerta"),
        _w("door"),
        _w("porta"),
        r"panel[_\s-]*puerta",
        r"puerta[_\s-]*panel",
    ],
    TipoInferido.lateral: [
        _w("lateral"),
        _w("lat"),
        _w("costado"),
        r"panel[_\s-]*lat",
        r"lat[_\s-]*panel",
    ],
    TipoInferido.fondo: [
        _w("fondo"),
        _w("trasero"),
        _w("respaldo"),
        _w("back"),
        r"panel[_\s-]*back",
        r"back[_\s-]*panel",
    ],
    TipoInferido.techo: [
        _w("techo"),
        _w("cubierta"),
        _w("superior"),
        _w("top"),
        r"tapa[_\s-]*sup",
        r"panel[_\s-]*top",
    ],
    TipoInferido.piso: [
        _w("piso"),
        _w("inferior"),
        _w("bottom"),
        _w("base"),
        r"panel[_\s-]*inf",
    ],
    TipoInferido.entrepaño: [
        r"entrepa[ñn]o",
        _w("shelf"),
        _w("estante"),
        _w("balda"),
        _w("repisa"),
        r"divisi[oó]n",
    ],
    TipoInferido.zocalo: [
        r"z[oó]calo",
        _w("kick"),
        _w("plinth"),
        _w("baseboard"),
        r"rodapi[eé]",
    ],
}

# Pre-compile all patterns for performance
_COMPILED: list[tuple[TipoInferido, list[re.Pattern[str]]]] = [
    (tipo, [re.compile(p, re.IGNORECASE) for p in patterns])
    for tipo, patterns in FURNITURE_TAXONOMY.items()
]


class NameClassifierTool:
    """Classify a component by its name using FURNITURE_TAXONOMY patterns."""

    CONFIDENCE = 0.92

    def classify(self, name: str) -> tuple[TipoInferido, float] | None:
        """
        Return (TipoInferido, confidence) if the name matches any taxonomy
        pattern, or None if no match is found.
        """
        normalized = name.strip()
        for tipo, patterns in _COMPILED:
            for pattern in patterns:
                if pattern.search(normalized):
                    return tipo, self.CONFIDENCE
        return None
