"""Integration test for check_version_lock.py using a real git repo."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_version_lock import LockResult, check_module  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    """Run a git command in the given repo."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a real git repo with a live module on main."""
    repo = tmp_path / "content"
    modules = repo / "modules" / "my-bank"
    assessment = modules / "assessment"
    assessment.mkdir(parents=True)

    # Initial commit on main with a live module
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    (modules / "module.yaml").write_text(
        yaml.dump({"moduleId": "my-bank", "status": "live", "order": 1})
    )
    (assessment / "assessment.yaml").write_text(
        yaml.dump({"version": 1, "title": "My Bank", "type": "uniform"})
    )
    (assessment / "question_001").mkdir()
    (assessment / "question_001" / "question.yaml").write_text(
        yaml.dump({"diagnosis": "adenoma"})
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    return repo


class TestIntegrationLiveVersionBump:
    """Integration: real git diff detects assessment changes."""

    def test_assessment_change_without_bump_fails(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Changing assessment content without bumping version fails."""
        modules = git_repo / "modules" / "my-bank"
        assessment = modules / "assessment"

        # Create a feature branch and modify assessment content
        _git(git_repo, "checkout", "-b", "feature/update")
        (assessment / "question_001" / "question.yaml").write_text(
            yaml.dump({"diagnosis": "serrated"})
        )
        _git(git_repo, "add", ".")
        _git(git_repo, "commit", "-m", "Change question")

        # Run version lock check against main (must be in repo root)
        monkeypatch.chdir(git_repo)
        result = LockResult()
        check_module(modules, "modules", "main", result)

        assert not result.passed
        assert "not bumped" in result.violations[0].message

    def test_assessment_change_with_bump_passes(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Changing assessment content with version bump passes."""
        modules = git_repo / "modules" / "my-bank"
        assessment = modules / "assessment"

        _git(git_repo, "checkout", "-b", "feature/bump")
        (assessment / "question_001" / "question.yaml").write_text(
            yaml.dump({"diagnosis": "serrated"})
        )
        (assessment / "assessment.yaml").write_text(
            yaml.dump({"version": 2, "title": "My Bank", "type": "uniform"})
        )
        _git(git_repo, "add", ".")
        _git(git_repo, "commit", "-m", "Bump version and change question")

        monkeypatch.chdir(git_repo)
        result = LockResult()
        check_module(modules, "modules", "main", result)

        assert result.passed

    def test_learning_change_without_bump_passes(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Changing learning content does not require a version bump."""
        modules = git_repo / "modules" / "my-bank"
        learning = modules / "learning"
        learning.mkdir(exist_ok=True)

        # Add learning content on main first
        (learning / "content.mdx").write_text("# Original")
        _git(git_repo, "add", ".")
        _git(git_repo, "commit", "-m", "Add learning")

        # Feature branch: change learning only
        _git(git_repo, "checkout", "-b", "feature/learn")
        (learning / "content.mdx").write_text("# Updated")
        _git(git_repo, "add", ".")
        _git(git_repo, "commit", "-m", "Update learning")

        monkeypatch.chdir(git_repo)
        result = LockResult()
        check_module(modules, "modules", "main", result)

        assert result.passed


class TestIntegrationDraft:
    """Integration: draft module rules with real git."""

    def test_draft_to_live_transition_with_assessment_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When main is draft, version must remain 1 even if changing."""
        repo = tmp_path / "content"
        modules = repo / "modules" / "new-bank"
        assessment = modules / "assessment"
        assessment.mkdir(parents=True)

        _git(repo, "init", "--initial-branch=main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")

        (modules / "module.yaml").write_text(
            yaml.dump({"moduleId": "new-bank", "status": "draft", "order": 1})
        )
        (assessment / "assessment.yaml").write_text(
            yaml.dump({"version": 1, "title": "New", "type": "uniform"})
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Initial draft")

        # Feature branch: try to set version 2 while still draft on main
        _git(repo, "checkout", "-b", "feature/premature-bump")
        (assessment / "assessment.yaml").write_text(
            yaml.dump({"version": 2, "title": "New", "type": "uniform"})
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Premature bump")

        monkeypatch.chdir(repo)
        result = LockResult()
        check_module(modules, "modules", "main", result)

        assert not result.passed
        assert "must stay at 1" in result.violations[0].message


class TestIntegrationRetired:
    """Integration: retired module blocks all changes."""

    def test_retired_module_blocks_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Any change to a retired module fails."""
        repo = tmp_path / "content"
        modules = repo / "modules" / "old-bank"
        assessment = modules / "assessment"
        assessment.mkdir(parents=True)

        _git(repo, "init", "--initial-branch=main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")

        (modules / "module.yaml").write_text(
            yaml.dump(
                {"moduleId": "old-bank", "status": "retired", "order": 1}
            )
        )
        (assessment / "assessment.yaml").write_text(
            yaml.dump({"version": 3, "title": "Old", "type": "uniform"})
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Retired module")

        # Feature branch: try to change something
        _git(repo, "checkout", "-b", "feature/fix-retired")
        (assessment / "assessment.yaml").write_text(
            yaml.dump({"version": 4, "title": "Old Fixed", "type": "uniform"})
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Try to fix retired")

        monkeypatch.chdir(repo)
        result = LockResult()
        check_module(modules, "modules", "main", result)

        assert not result.passed
        assert "frozen" in result.violations[0].message
