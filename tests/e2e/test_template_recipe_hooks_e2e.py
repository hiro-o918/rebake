"""End-to-end specification for template-side recipe hooks.

All scenarios are written input-first: the recipe YAML, any user edits to
rebake.yaml, and the expected post-condition (rebake.yaml content + log
file content) are spelled out in each test body so the contract is readable
at a glance.

Most tests are marked xfail(strict=True) until the implementation lands.
PR2 wires the internals (recipe loader + CruftConfig.template_hooks).
PR3 connects create.py / update.py and removes these xfail markers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rebake.cli import app

runner = CliRunner()


# Marker reused on every test; the explicit reason makes it easy to grep for
# when removing in PR3.
xfail_until_implemented = pytest.mark.xfail(
    strict=True,
    reason="template recipe hooks not yet wired (implemented in PR2/PR3)",
)


def _head_commit(repo: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _render_project(template_repo: Path, output_dir: Path) -> Path:
    """Render the template into output_dir and return the rendered project path."""
    output_dir.mkdir(exist_ok=True)
    result = runner.invoke(
        app,
        ["create", str(template_repo), "--output-dir", str(output_dir)],
        input="my-project\n",
    )
    assert result.exit_code == 0, result.output
    return output_dir / "my-project"


def _init_git(project_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=project_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project_dir, capture_output=True, check=True)


def _write_recipe(template_repo: Path, recipe: dict) -> None:
    """Overwrite rebake-recipe.yaml in the template and commit the change."""
    (template_repo / "rebake-recipe.yaml").write_text(yaml.dump(recipe, sort_keys=False))
    subprocess.run(["git", "add", "."], cwd=template_repo, check=True)
    subprocess.run(["git", "commit", "-m", "update recipe"], cwd=template_repo, check=True)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@xfail_until_implemented
def test_create_with_recipe_writes_full_rebake_yaml(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """rebake create populates rebake.yaml with template_hooks copied from the recipe.

    Given:
      template_with_recipe fixture containing a rebake-recipe.yaml with both
      pre-update and post-update hooks.

    When:
      rebake create runs against that template.

    Then:
      The generated rebake.yaml contains: template / commit / context /
      template_hooks. No user-side hooks.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")
    commit = _head_commit(template_repo_with_recipe)

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "template_hooks": {
            "pre-update": ['echo "template pre-update: $REBAKE_NEW_COMMIT" > "$REBAKE_PROJECT_DIR/template_pre.log"'],
            "post-update": ['echo "template post-update: $REBAKE_GIT_ROOT" > "$REBAKE_PROJECT_DIR/template_post.log"'],
        },
    }


@pytest.mark.e2e
def test_create_without_recipe_writes_no_template_hooks(tmp_path: Path, template_repo: Path) -> None:
    """A template without rebake-recipe.yaml produces a rebake.yaml without template_hooks.

    Given:
      simple_template fixture (no rebake-recipe.yaml).

    When:
      rebake create runs.

    Then:
      The generated rebake.yaml contains: template / commit / context only.
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    result = runner.invoke(
        app,
        ["create", str(template_repo), "--output-dir", str(output_dir)],
        input="my-project\n",
    )
    assert result.exit_code == 0, result.output
    commit = _head_commit(template_repo)

    data = yaml.safe_load((output_dir / "my-project" / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo),
        "commit": commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
    }


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@xfail_until_implemented
def test_update_refreshes_template_hooks_from_changed_recipe(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """rebake update overwrites template_hooks with the recipe at the new commit.

    Given:
      A project created from the fixture (pre-update + post-update template_hooks).
      The template's rebake-recipe.yaml is then rewritten to keep only a single
      post-update hook, and that change is committed.

    When:
      rebake update runs.

    Then:
      rebake.yaml.template_hooks contains only post-update (pre-update is gone),
      reflecting the new recipe verbatim. The bumped commit is also persisted.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")
    _init_git(project)

    refreshed_recipe = {
        "hooks": {
            "post-update": ['echo "refreshed" > "$REBAKE_PROJECT_DIR/refreshed.log"'],
        }
    }
    _write_recipe(template_repo_with_recipe, refreshed_recipe)
    new_commit = _head_commit(template_repo_with_recipe)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": new_commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "template_hooks": {
            "post-update": ['echo "refreshed" > "$REBAKE_PROJECT_DIR/refreshed.log"'],
        },
    }


@pytest.mark.e2e
@xfail_until_implemented
def test_update_preserves_user_hooks_and_refreshes_template_hooks(
    tmp_path: Path, template_repo_with_recipe: Path
) -> None:
    """User-defined hooks survive update. template_hooks gets refreshed independently.

    Given:
      A freshly created project. The user adds their own post-update hook to
      rebake.yaml.hooks. The template's recipe is then changed (the post-update
      entry is replaced; pre-update is dropped) and a new commit is made on the
      template.

    When:
      rebake update runs.

    Then:
      rebake.yaml.hooks (user-side) is untouched, and rebake.yaml.template_hooks
      reflects the new recipe.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")

    user_hooks = {"post-update": ['echo "user" > "$REBAKE_PROJECT_DIR/user.log"']}
    rebake_yaml = yaml.safe_load((project / "rebake.yaml").read_text())
    rebake_yaml["hooks"] = user_hooks
    (project / "rebake.yaml").write_text(yaml.dump(rebake_yaml, allow_unicode=True, sort_keys=False))

    _init_git(project)

    refreshed_recipe = {
        "hooks": {
            "post-update": ['echo "refreshed" > "$REBAKE_PROJECT_DIR/refreshed.log"'],
        }
    }
    _write_recipe(template_repo_with_recipe, refreshed_recipe)
    new_commit = _head_commit(template_repo_with_recipe)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load((project / "rebake.yaml").read_text())

    assert data == {
        "template": str(template_repo_with_recipe),
        "commit": new_commit,
        "context": {"cookiecutter": {"project_name": "my-project"}},
        "template_hooks": {
            "post-update": ['echo "refreshed" > "$REBAKE_PROJECT_DIR/refreshed.log"'],
        },
        "hooks": user_hooks,
    }


@pytest.mark.e2e
@xfail_until_implemented
def test_update_runs_template_hooks_before_user_hooks(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """For each event, template hooks fire before user hooks.

    Given:
      A project whose recipe defines pre/post hooks that append "template-pre"
      and "template-post" to order.log. The user adds pre/post hooks that append
      "user-pre" and "user-post" to the same file.

    When:
      rebake update runs.

    Then:
      order.log records the four entries in this exact order:
        template-pre, user-pre, template-post, user-post.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")

    order_recipe = {
        "hooks": {
            "pre-update": ['echo "template-pre" >> "$REBAKE_PROJECT_DIR/order.log"'],
            "post-update": ['echo "template-post" >> "$REBAKE_PROJECT_DIR/order.log"'],
        }
    }
    _write_recipe(template_repo_with_recipe, order_recipe)

    rebake_yaml = yaml.safe_load((project / "rebake.yaml").read_text())
    rebake_yaml["hooks"] = {
        "pre-update": ['echo "user-pre" >> "$REBAKE_PROJECT_DIR/order.log"'],
        "post-update": ['echo "user-post" >> "$REBAKE_PROJECT_DIR/order.log"'],
    }
    (project / "rebake.yaml").write_text(yaml.dump(rebake_yaml, allow_unicode=True, sort_keys=False))
    _init_git(project)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    assert (project / "order.log").read_text() == ("template-pre\nuser-pre\ntemplate-post\nuser-post\n")


# ---------------------------------------------------------------------------
# REBAKE_GIT_ROOT environment variable
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@xfail_until_implemented
def test_rebake_git_root_equals_project_dir_in_standalone_repo(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """REBAKE_GIT_ROOT exposes the enclosing git work tree root.

    Given:
      A freshly created project that is its own git repo (standalone layout).
      The fixture's post-update hook echoes "template post-update: $REBAKE_GIT_ROOT".

    When:
      rebake update runs.

    Then:
      template_post.log contains the project directory as the git root.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")
    _init_git(project)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    assert (project / "template_post.log").read_text() == f"template post-update: {project.resolve()}\n"


@pytest.mark.e2e
@xfail_until_implemented
def test_rebake_git_root_points_to_outer_repo_in_monorepo(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """REBAKE_GIT_ROOT walks up to the enclosing git root in a monorepo layout.

    Given:
      A monorepo git work tree at <tmp>/monorepo. The generated project lives
      at <tmp>/monorepo/packages/my-project and is NOT a git repo of its own.

    When:
      rebake update runs from inside the project.

    Then:
      template_post.log records the monorepo root (not the project dir).
    """
    monorepo = tmp_path / "monorepo"
    monorepo.mkdir()
    subprocess.run(["git", "init"], cwd=monorepo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=monorepo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=monorepo, capture_output=True, check=True)
    (monorepo / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "."], cwd=monorepo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init monorepo"], cwd=monorepo, capture_output=True, check=True)

    project = _render_project(template_repo_with_recipe, monorepo / "packages")
    subprocess.run(["git", "add", "."], cwd=monorepo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add project"], cwd=monorepo, capture_output=True, check=True)

    result = runner.invoke(app, ["update", str(project)])
    assert result.exit_code == 0, result.output

    assert (project / "template_post.log").read_text() == f"template post-update: {monorepo.resolve()}\n"


@pytest.mark.e2e
@xfail_until_implemented
def test_rebake_git_root_is_empty_string_outside_git(tmp_path: Path, template_repo_with_recipe: Path) -> None:
    """REBAKE_GIT_ROOT is "" when the project is not inside any git work tree.

    Given:
      A freshly created project with NO git init (the project sits outside
      any git tree).

    When:
      rebake update runs with --allow-untracked-files (the clean-tree check
      requires a git repo to be meaningful).

    Then:
      template_post.log records the prefix only, with REBAKE_GIT_ROOT expanded
      to an empty string.
    """
    project = _render_project(template_repo_with_recipe, tmp_path / "output")

    result = runner.invoke(app, ["update", str(project), "--allow-untracked-files"])
    assert result.exit_code == 0, result.output

    assert (project / "template_post.log").read_text() == "template post-update: \n"
