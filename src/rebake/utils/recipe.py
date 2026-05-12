from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict, cast

import yaml

RECIPE_FILE = "rebake-recipe.yaml"

# Hook events fired around `rebake update`. Defined via the functional TypedDict
# form because the keys contain a hyphen, which is not a valid Python identifier
# in the class-based form. `total=False` lets a recipe declare only one of the
# two events without satisfying the other.
HookSpec = TypedDict(
    "HookSpec",
    {
        "pre-update": list[str],
        "post-update": list[str],
    },
    total=False,
)


@dataclass
class Recipe:
    """Template-side rebake recipe.

    Declares default hooks the template author wants applied to every
    generated project. Loaded from rebake-recipe.yaml at the template root
    and inherited into the generated project's rebake.yaml.template_hooks.
    """

    hooks: HookSpec = field(default_factory=lambda: cast(HookSpec, {}))


def load_recipe(template_dir: Path) -> Recipe:
    """Load rebake-recipe.yaml from a cloned template directory.

    Returns an empty Recipe when the file is absent (template authors that
    do not need template-side hooks are unaffected).

    Raises ValueError when the file exists but has an unexpected shape, so
    template authoring mistakes fail loudly instead of silently dropping hooks.
    """
    recipe_path = template_dir / RECIPE_FILE
    if not recipe_path.exists():
        return Recipe()

    raw = yaml.safe_load(recipe_path.read_text())
    if raw is None:
        return Recipe()
    if not isinstance(raw, dict):
        raise ValueError(f"{RECIPE_FILE}: top-level must be a mapping, got {type(raw).__name__}")

    hooks_raw = raw.get("hooks", {})
    if not isinstance(hooks_raw, dict):
        raise ValueError(f"{RECIPE_FILE}: 'hooks' must be a mapping, got {type(hooks_raw).__name__}")

    valid_events = tuple(HookSpec.__annotations__.keys())
    hooks: dict[str, list[str]] = {}
    for event, commands in hooks_raw.items():
        if event not in valid_events:
            raise ValueError(f"{RECIPE_FILE}: unsupported hook event {event!r} (expected one of {valid_events})")
        if not isinstance(commands, list) or not all(isinstance(c, str) for c in commands):
            raise ValueError(f"{RECIPE_FILE}: hooks.{event} must be a list of strings")
        hooks[event] = list(commands)

    return Recipe(hooks=cast(HookSpec, hooks))
