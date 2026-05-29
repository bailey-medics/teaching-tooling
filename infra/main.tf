# main.tf — GitHub branch protection for teaching repositories
#
# Uses organisation-level rulesets that auto-apply to any repository
# matching the "*-teaching" name pattern. No per-repo config needed
# when onboarding a new content repo — just name it *-teaching.
#
# Usage:
#   cd infra/
#   terraform init
#   terraform plan -var-file=terraform.tfvars
#   terraform apply -var-file=terraform.tfvars

terraform {
  required_version = ">= 1.5.7"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

provider "github" {
  owner = var.github_owner
}

# ---------------------------------------------------------------------------
# Org-level Ruleset 1 — Content repos: protected branches
# ---------------------------------------------------------------------------
# Targets: all repos matching *-teaching
#
# Prevents direct pushes, force pushes, and branch deletion on main.
# Requires a PR and the Validate CI workflow to pass before merging.

resource "github_organization_ruleset" "teaching_protected_branches" {
  name        = "teaching-content-protected-branches"
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["refs/heads/main"]
      exclude = []
    }

    repository_name {
      include = ["~*-teaching"]
      exclude = []
    }
  }

  rules {
    pull_request {
      required_approving_review_count   = 0
      dismiss_stale_reviews_on_push     = true
      require_code_owner_review         = false
      require_last_push_approval        = false
      required_review_thread_resolution = false
    }

    required_status_checks {
      strict_required_status_checks_policy = true

      required_check {
        context = "Validate / validate / validate"
      }
    }

    non_fast_forward = true
    deletion         = true
  }
}

# ---------------------------------------------------------------------------
# Org-level Ruleset 2 — Content repos: branch naming convention
# ---------------------------------------------------------------------------
# Targets: all branches except main in *-teaching repos

resource "github_organization_ruleset" "teaching_branch_naming" {
  name        = "teaching-content-branch-naming"
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~ALL"]
      exclude = ["refs/heads/main"]
    }

    repository_name {
      include = ["~*-teaching"]
      exclude = []
    }
  }

  rules {
    branch_name_pattern {
      operator = "regex"
      pattern  = "^(feature|hotfix|copilot|renovate)/.+"
      name     = "Branch names must follow feature/*, hotfix/*, copilot/*, or renovate/* convention"
      negate   = false
    }
  }
}

# ---------------------------------------------------------------------------
# Repo-level Ruleset 3 — teaching-tooling: protected branches
# ---------------------------------------------------------------------------

resource "github_repository_ruleset" "tooling_protected_branches" {
  name        = "protected-branches"
  repository  = "teaching-tooling"
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["refs/heads/main"]
      exclude = []
    }
  }

  rules {
    pull_request {
      required_approving_review_count   = 0
      dismiss_stale_reviews_on_push     = true
      require_code_owner_review         = false
      require_last_push_approval        = false
      required_review_thread_resolution = false
    }

    required_status_checks {
      strict_required_status_checks_policy = true

      required_check {
        context = "python-tests"
      }
      required_check {
        context = "node-tests"
      }
    }

    non_fast_forward = true
    deletion         = true
  }
}

# ---------------------------------------------------------------------------
# Repo-level Ruleset 4 — teaching-tooling: branch naming convention
# ---------------------------------------------------------------------------

resource "github_repository_ruleset" "tooling_branch_naming" {
  name        = "branch-naming-convention"
  repository  = "teaching-tooling"
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~ALL"]
      exclude = ["refs/heads/main"]
    }
  }

  rules {
    branch_name_pattern {
      operator = "regex"
      pattern  = "^(feature|hotfix|copilot|renovate)/.+"
      name     = "Branch names must follow feature/*, hotfix/*, copilot/*, or renovate/* convention"
      negate   = false
    }
  }
}
