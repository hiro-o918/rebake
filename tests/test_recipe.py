from __future__ import annotations

import pytest
import yaml

from rebake.utils.recipe import RECIPE_FILE, Recipe, load_recipe


def test_load_recipe_missing_file_returns_empty(tmp_path):
    recipe = load_recipe(tmp_path)

    assert recipe == Recipe()


def test_load_recipe_empty_yaml_returns_empty(tmp_path):
    (tmp_path / RECIPE_FILE).write_text("")

    recipe = load_recipe(tmp_path)

    assert recipe == Recipe()


def test_load_recipe_parses_hooks(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(
        yaml.dump(
            {
                "hooks": {
                    "pre-update": ["echo pre"],
                    "post-update": ["echo post-1", "echo post-2"],
                }
            }
        )
    )

    recipe = load_recipe(tmp_path)

    assert recipe.hooks == {
        "pre-update": ["echo pre"],
        "post-update": ["echo post-1", "echo post-2"],
    }


def test_load_recipe_without_hooks_key_returns_empty_hooks(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"other": "value"}))

    recipe = load_recipe(tmp_path)

    assert recipe.hooks == {}


def test_load_recipe_rejects_non_mapping_top_level(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(yaml.dump(["just", "a", "list"]))

    with pytest.raises(ValueError, match="top-level must be a mapping"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_non_mapping_hooks(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": ["pre-update"]}))

    with pytest.raises(ValueError, match="'hooks' must be a mapping"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_unknown_event(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": {"pre-create": ["echo"]}}))

    with pytest.raises(ValueError, match="unsupported hook event"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_non_string_command(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(
        yaml.dump({"hooks": {"pre-update": [{"cmd": "echo hi"}]}}),
    )

    with pytest.raises(ValueError, match="must be a list of strings"):
        load_recipe(tmp_path)


def test_load_recipe_rejects_non_list_commands(tmp_path):
    (tmp_path / RECIPE_FILE).write_text(yaml.dump({"hooks": {"pre-update": "echo single"}}))

    with pytest.raises(ValueError, match="must be a list of strings"):
        load_recipe(tmp_path)
