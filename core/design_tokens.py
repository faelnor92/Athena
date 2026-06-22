"""Extraction AUTOMATIQUE d'un design system (charte), pour la parité avec Claude Design.

Trois sources :
  - `from_codebase` : DÉTERMINISTE (sans LLM) — lit les fichiers du projet (variables CSS du
    `:root`, couleurs hex/rgb, `font-family`, `border-radius`, config Tailwind) et synthétise
    une charte. Idéal quand un projet existe déjà.
  - `from_image` : via la VISION (modèle multimodal) — extrait palette/typo/style d'une capture
    ou d'une maquette.
  - `from_brief` : via le LLM — déduit une charte de départ d'une simple description (cas
    GREENFIELD : pas de code → on fige palette/typo dès la v1 au lieu de laisser diverger).

Tout est défensif : en cas d'échec, renvoie "".
"""
import os
import re
from collections import Counter

_CSS_EXT = (".css", ".scss", ".sass", ".less")
_CODE_EXT = (".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro")
_IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
                ".next", ".chroma_db", ".idea", ".vscode"}


def _gather(workspace_dir: str, max_files: int = 500, max_bytes: int = 3_000_000):
    """Concatène le CSS/markup du projet + le contenu des configs Tailwind. Renvoie (css, tw)."""
    css_parts, tw_parts, total, n = [], [], 0, 0
    for root, dirs, files in os.walk(workspace_dir):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
        for fn in files:
            if n >= max_files or total >= max_bytes:
                return "\n".join(css_parts), "\n".join(tw_parts)
            low = fn.lower()
            is_tw = low.startswith("tailwind.config")
            if not (is_tw or low.endswith(_CSS_EXT) or low.endswith(_CODE_EXT)):
                continue
            try:
                with open(os.path.join(root, fn), "r", encoding="utf-8", errors="ignore") as f:
                    data = f.read(200_000)
            except Exception:
                continue
            total += len(data)
            n += 1
            (tw_parts if is_tw else css_parts).append(data)
    return "\n".join(css_parts), "\n".join(tw_parts)


def from_codebase(workspace_dir: str) -> str:
    """Charte déduite des fichiers du projet (déterministe, sans LLM). "" si rien d'exploitable."""
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return ""
    css, tw = _gather(workspace_dir)
    blob = css + "\n" + tw
    if not blob.strip():
        return ""

    lines = []

    # Couleurs : variables CSS de marque d'abord, sinon hex les plus fréquents.
    brand_vars = re.findall(r"(--[\w-]*(?:color|brand|accent|primary|secondary|bg|surface)[\w-]*)\s*:\s*([^;\}\n]+)",
                            blob, re.IGNORECASE)
    if brand_vars:
        seen, pairs = set(), []
        for name, val in brand_vars:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                pairs.append(f"{name}: {val.strip()}")
        lines.append("Variables de marque : " + " ; ".join(pairs[:10]))
    hexes = Counter(re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", blob))
    if hexes:
        lines.append("Couleurs dominantes : " + ", ".join(c for c, _ in hexes.most_common(8)))

    # Typographie.
    fonts = Counter(re.findall(r"font-family\s*:\s*([^;\}\n]+)", blob, re.IGNORECASE))
    if fonts:
        top = "; ".join(f.strip().strip("\"'") for f, _ in fonts.most_common(3))
        lines.append("Typographie : " + top)

    # Arrondis.
    radii = Counter(re.findall(r"border-radius\s*:\s*([0-9.]+(?:px|rem|em|%))", blob, re.IGNORECASE))
    if radii:
        lines.append("Arrondis (border-radius) fréquents : " + ", ".join(r for r, _ in radii.most_common(4)))

    # Tailwind : palette + polices déclarées dans theme.extend.
    if tw:
        tw_colors = re.findall(r"['\"]?(#[0-9a-fA-F]{3,6})['\"]?", tw)
        tw_fonts = re.findall(r"fontFamily\s*:\s*\{([^}]*)\}", tw, re.IGNORECASE)
        if tw_colors:
            uniq = list(dict.fromkeys(tw_colors))[:8]
            lines.append("Palette Tailwind : " + ", ".join(uniq))
        if tw_fonts:
            fams = re.findall(r"['\"]([A-Za-z0-9 _-]+)['\"]", tw_fonts[0])
            if fams:
                lines.append("Polices Tailwind : " + ", ".join(dict.fromkeys(fams))[:120])

    return "\n".join(lines).strip()


def _complete(messages, max_tokens=700):
    from core.state import swarm as _sw
    from core.athenadesign_generator import _athena_default_model
    resp = _sw._complete(_athena_default_model(), messages, tools_schema=None,
                         allow_continuation=True, allow_fallback=True, max_tokens=max_tokens)
    return (resp.choices[0].message.content or "").strip()


_CHARTE_INSTR = (
    "Tu es un directeur artistique. Produis une CHARTE GRAPHIQUE concise et ACTIONNABLE en "
    "français (8 lignes max) : palette (couleurs en hex), typographie (familles), arrondis, "
    "espacement, ton/ambiance. Pas de phrases inutiles, juste la charte."
)


def from_image(images: list) -> str:
    """Charte extraite d'une ou plusieurs images via un modèle vision. "" si indisponible."""
    images = [u for u in (images or []) if u]
    if not images:
        return ""
    try:
        from core.athenadesign_generator import _athena_default_model, _model_supports_vision, _describe_images
        model = _athena_default_model()
        if _model_supports_vision(model):
            content = [{"type": "text", "text": _CHARTE_INSTR}] + [
                {"type": "image_url", "image_url": {"url": u}} for u in images[:4]]
            return _complete([{"role": "user", "content": content}])
        # Repli : pré-description par un VISION_MODEL, puis synthèse texte.
        desc = _describe_images(images)
        if not desc:
            return ""
        return _complete([{"role": "system", "content": _CHARTE_INSTR},
                          {"role": "user", "content": "Description visuelle :\n" + desc}])
    except Exception:
        return ""


def from_brief(brief: str) -> str:
    """Charte de DÉPART déduite d'une description (cas greenfield, sans code). "" si échec."""
    brief = (brief or "").strip()
    if not brief:
        return ""
    try:
        return _complete([{"role": "system", "content": _CHARTE_INSTR},
                          {"role": "user", "content": "Projet : " + brief}])
    except Exception:
        return ""
