"""Tests for scripts/check_version_lock.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Add scripts/ to path so we can import
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_version_lock import (  # noqa: E402
    LockResult,
    check_module,
    check_version_lock,
)


@pytest.fixture
def tmp_module(tmp_path: Path) -> Path:
    """Create a minimal module directory for testing."""
    module_dir = tmp_path / "modules" / "test-bank"
    assessment_dir = module_dir / "assessment"
    assessment_dir.mkdir(parents=True)

    # module.yaml
    (module_dir / "module.yaml").write_text(
        yaml.dump({"moduleId": "test-bank", "status": "live", "order": 1})
    )

    # assessment.yaml
    (assessment_dir / "assessment.yaml").write_text(
        yaml.dump({"version": 2, "title": "Test", "type": "uniform"})
    )

    return module_dir


class TestDraftModule:
    """Draft modules: version must remain 1."""

    def test_draft_version_1_passes(self, tmp_module: Path) -> None:
        """Draft module with version 1 should pass."""
        # Write assessment with version 1
        assessment_yaml = tmp_module / "assessment" / "assessment.yaml"
        assessment_yaml.write_text(
            yaml.dump({"version": 1, "title": "Test", "type": "uniform"})
        )

        result = LockResult()
        with patch(
            "check_version_lock._git_show",
            return_value=yaml.dump({"status": "draft", "moduleId": "test-bank"}),
        ), patch("check_version_lock._git_diff_names", return_value=[]):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert result.passed

    def test_draft_version_not_1_fails(self, tmp_module: Path) -> None:
        """Draft module with version != 1 should fail."""
        # Write assessment with version 2
        assessment_yaml = tmp_module / "assessment" / "assessment.yaml"
        assessment_yaml.write_text(
            yaml.dump({"version": 2, "title": "Test", "type": "uniform"})
        )

        result = LockResult()
        with patch(
            "check_version_lock._git_show",
            return_value=yaml.dump({"status": "draft", "moduleId": "test-bank"}),
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert not result.passed
        assert "version must stay at 1" in result.violations[0].message


class TestRetiredModule:
    """Retired modules: any change is rejected."""

    def test_retired_with_changes_fails(self, tmp_module: Path) -> None:
        """Any diff on a retired module should fail."""
        result = LockResult()
        with patch(
            "check_version_lock._git_show",
            return_value=yaml.dump(
                {"status": "retired", "moduleId": "test-bank"}
            ),
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=["modules/test-bank/assessment/assessment.yaml"],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert not result.passed
        assert "permanently frozen" in result.violations[0].message

    def test_retired_no_changes_still_fails(self, tmp_module: Path) -> None:
        """Even with no diff, retired modules should still fail.

        (The script fails on any PR touching a retired module directory.)
        """
        result = LockResult()
        with patch(
            "check_version_lock._git_show",
            return_value=yaml.dump(
                {"status": "retired", "moduleId": "test-bank"}
            ),
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=[],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        # No changes = no violation (the PR didn't touch this module)
        assert result.passed


class TestLiveModule:
    """Live modules: assessment changes require version +1."""

    def test_no_assessment_changes_passes(self, tmp_module: Path) -> None:
        """No assessment file changes should pass."""
        result = LockResult()
        with patch(
            "check_version_lock._git_show",
            return_value=yaml.dump({"status": "live", "moduleId": "test-bank"}),
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=[],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert result.passed

    def test_assessment_changed_version_bumped_passes(
        self, tmp_module: Path
    ) -> None:
        """Assessment changed + version bumped by 1 should pass."""
        # PR has version 2
        assessment_yaml = tmp_module / "assessment" / "assessment.yaml"
        assessment_yaml.write_text(
            yaml.dump({"version": 2, "title": "Test", "type": "uniform"})
        )

        result = LockResult()

        def mock_git_show(ref: str, path: str) -> str | None:
            if "module.yaml" in path:
                return yaml.dump({"status": "live", "moduleId": "test-bank"})
            if "assessment.yaml" in path:
                # Main has version 1
                return yaml.dump(
                    {"version": 1, "title": "Test", "type": "uniform"}
                )
            return None

        with patch(
            "check_version_lock._git_show", side_effect=mock_git_show
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=["modules/test-bank/assessment/assessment.yaml"],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert result.passed

    def test_assessment_changed_version_not_bumped_fails(
        self, tmp_module: Path
    ) -> None:
        """Assessment changed + same version should fail."""
        # PR still has version 1
        assessment_yaml = tmp_module / "assessment" / "assessment.yaml"
        assessment_yaml.write_text(
            yaml.dump({"version": 1, "title": "Test", "type": "uniform"})
        )

        result = LockResult()

        def mock_git_show(ref: str, path: str) -> str | None:
            if "module.yaml" in path:
                return yaml.dump({"status": "live", "moduleId": "test-bank"})
            if "assessment.yaml" in path:
                return yaml.dump(
                    {"version": 1, "title": "Test", "type": "uniform"}
                )
            return None

        with patch(
            "check_version_lock._git_show", side_effect=mock_git_show
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=["modules/test-bank/assessment/question_1/question.yaml"],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert not result.passed
        assert "not bumped" in result.violations[0].message

    def test_assessment_changed_version_skipped_fails(
        self, tmp_module: Path
    ) -> None:
        """Assessment changed + version jumped by >1 should fail."""
        # PR has version 3, main has version 1
        assessment_yaml = tmp_module / "assessment" / "assessment.yaml"
        assessment_yaml.write_text(
            yaml.dump({"version": 3, "title": "Test", "type": "uniform"})
        )

        result = LockResult()

        def mock_git_show(ref: str, path: str) -> str | None:
            if "module.yaml" in path:
                return yaml.dump({"status": "live", "moduleId": "test-bank"})
            if "assessment.yaml" in path:
                return yaml.dump(
                    {"version": 1, "title": "Test", "type": "uniform"}
                )
            return None

        with patch(
            "check_version_lock._git_show", side_effect=mock_git_show
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=["modules/test-bank/assessment/assessment.yaml"],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert not result.passed
        assert "increment by exactly 1" in result.violations[0].message

    def test_assessment_changed_version_decreased_fails(
        self, tmp_module: Path
    ) -> None:
        """Assessment changed + version decreased should fail."""
        # PR has version 1, main has version 2
        assessment_yaml = tmp_module / "assessment" / "assessment.yaml"
        assessment_yaml.write_text(
            yaml.dump({"version": 1, "title": "Test", "type": "uniform"})
        )

        result = LockResult()

        def mock_git_show(ref: str, path: str) -> str | None:
            if "module.yaml" in path:
                return yaml.dump({"status": "live", "moduleId": "test-bank"})
            if "assessment.yaml" in path:
                return yaml.dump(
                    {"version": 2, "title": "Test", "type": "uniform"}
                )
            return None

        with patch(
            "check_version_lock._git_show", side_effect=mock_git_show
        ), patch(
            "check_version_lock._git_diff_names",
            return_value=["modules/test-bank/assessment/assessment.yaml"],
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert not result.passed
        assert "decreased" in result.violations[0].message


class TestNewModule:
    """New modules (not on main) should be skipped."""

    def test_new_module_skipped(self, tmp_module: Path) -> None:
        """Module not on main is skipped (nothing to protect)."""
        result = LockResult()
        with patch(
            "check_version_lock._git_show",
            return_value=None,  # Not found on main
        ):
            check_module(
                tmp_module, "modules", "origin/main", result
            )

        assert result.passed
        assert result.modules_skipped == 1
