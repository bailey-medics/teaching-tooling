"""Version lock enforcement for live teaching modules.

Checks that assessment changes in a PR include the required version bump.
Runs in CI against the PR branch, comparing to origin/main.

Rules by module status on main:
- draft: version must remain 1
- retired: no changes allowed (permanently frozen)
- live: assessment changes require version +1

Usage:
    python scripts/check_version_lock.py <modules-directory>

Exit codes:
    0 — all modules pass version lock checks
    1 — one or more violations found
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LockViolation:
    """A single version lock violation."""

    module_id: str
    message: str

    def __str__(self) -> str:
        return f"  FAIL [{self.module_id}]: {self.message}"


@dataclass
class LockResult:
    """Aggregate result for all modules checked."""

    violations: list[LockViolation] = field(default_factory=list)
    modules_checked: int = 0
    modules_skipped: int = 0

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0

    def add_violation(self, module_id: str, message: str) -> None:
        self.violations.append(
            LockViolation(module_id=module_id, message=message)
        )

    def summary(self) -> str:
        lines = [
            f"Version lock: checked {self.modules_checked} module(s), "
            f"skipped {self.modules_skipped}."
        ]
        if self.passed:
            lines.append("All passed.")
        else:
            lines.append(f"{len(self.violations)} violation(s):")
            for v in self.violations:
                lines.append(str(v))
        return "\n".join(lines)


def _git_show(ref: str, path: str) -> str | None:
    """Read a file from a git ref. Returns None if file doesn't exist."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def _git_diff_names(ref: str, path: str) -> list[str]:
    """Get list of changed files under a path relative to a ref."""
    result = subprocess.run(
        ["git", "diff", "--name-only", ref, "--", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line.strip() for line in result.stdout.splitlines() if line.strip()
    ]


def _load_yaml(content: str) -> dict[str, Any] | None:
    """Parse YAML content, returning None on failure."""
    try:
        data = yaml.safe_load(content)
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


def _get_assessment_version(module_dir: Path) -> int | None:
    """Read version from the PR branch's assessment.yaml."""
    for name in ("assessment.yaml", "config.yaml"):
        path = module_dir / "assessment" / name
        if path.is_file():
            with open(path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                version = data.get("version")
                if isinstance(version, int):
                    return version
    return None


def _get_main_assessment_version(
    ref: str, modules_rel_path: str, module_id: str
) -> int | None:
    """Read version from main's assessment.yaml."""
    for name in ("assessment.yaml", "config.yaml"):
        content = _git_show(
            ref, f"{modules_rel_path}/{module_id}/assessment/{name}"
        )
        if content is not None:
            data = _load_yaml(content)
            if data is not None:
                version = data.get("version")
                if isinstance(version, int):
                    return version
    return None


def check_module(
    module_dir: Path,
    modules_rel_path: str,
    ref: str,
    result: LockResult,
) -> None:
    """Check version lock rules for a single module."""
    module_id = module_dir.name
    result.modules_checked += 1

    # Read module.yaml from main
    main_module_content = _git_show(
        ref, f"{modules_rel_path}/{module_id}/module.yaml"
    )

    if main_module_content is None:
        # New module — nothing to protect
        result.modules_skipped += 1
        return

    main_module = _load_yaml(main_module_content)
    if main_module is None:
        result.modules_skipped += 1
        return

    main_status = main_module.get("status")

    if main_status == "draft":
        # Version must remain 1
        pr_version = _get_assessment_version(module_dir)
        if pr_version is not None and pr_version != 1:
            result.add_violation(
                module_id,
                f"version must stay at 1 while module is draft "
                f"(found {pr_version})",
            )
        return

    if main_status == "retired":
        # No changes allowed at all
        changed = _git_diff_names(ref, f"{modules_rel_path}/{module_id}/")
        if changed:
            result.add_violation(
                module_id,
                "retired modules are permanently frozen; "
                "create a new module instead "
                f"({len(changed)} file(s) changed)",
            )
        return

    if main_status == "live":
        # Assessment changes require version bump +1
        changed_assessment = _git_diff_names(
            ref, f"{modules_rel_path}/{module_id}/assessment/"
        )

        if not changed_assessment:
            # No assessment files changed — pass
            return

        main_version = _get_main_assessment_version(
            ref, modules_rel_path, module_id
        )
        pr_version = _get_assessment_version(module_dir)

        if main_version is None:
            result.add_violation(
                module_id,
                "cannot read version from main's assessment.yaml",
            )
            return

        if pr_version is None:
            result.add_violation(
                module_id,
                "cannot read version from PR's assessment.yaml",
            )
            return

        if pr_version == main_version:
            result.add_violation(
                module_id,
                f"assessment files changed but version not bumped "
                f"(still {main_version})",
            )
        elif pr_version == main_version + 1:
            pass  # Correct
        elif pr_version > main_version + 1:
            result.add_violation(
                module_id,
                f"version jumped from {main_version} to {pr_version} "
                f"(must increment by exactly 1)",
            )
        elif pr_version < main_version:
            result.add_violation(
                module_id,
                f"version decreased from {main_version} to {pr_version}",
            )
        return

    # Unknown status — skip with no error (validate.py handles schema)
    result.modules_skipped += 1


def check_version_lock(
    modules_dir: Path, ref: str = "origin/main"
) -> LockResult:
    """Check version lock for all modules in a directory.

    Args:
        modules_dir: Path to the modules/ directory (PR branch).
        ref: Git ref to compare against (default: origin/main).

    Returns:
        LockResult with any violations found.
    """
    result = LockResult()

    if not modules_dir.is_dir():
        result.add_violation("(root)", "modules/ directory not found")
        return result

    # Determine the relative path from the repo root to modules/
    # This is needed for git show/diff commands
    repo_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    repo_root = Path(repo_root_result.stdout.strip())
    modules_rel_path = str(modules_dir.resolve().relative_to(repo_root))

    module_dirs = sorted(
        d
        for d in modules_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    for module_dir in module_dirs:
        check_module(module_dir, modules_rel_path, ref, result)

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        print(
            "Usage: python scripts/check_version_lock.py <modules-directory>"
        )
        return 1

    modules_path = Path(args[0])
    result = check_version_lock(modules_path)
    print(result.summary())
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
