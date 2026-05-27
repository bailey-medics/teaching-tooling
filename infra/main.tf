terraform {
  required_version = ">= 1.5"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

provider "github" {
  owner = "bailey-medics"
}

locals {
  teaching_repos = toset([
    "eoeeta-teaching",
    "respiratory-teaching",
  ])

  all_teaching_repos = toset([
    "eoeeta-teaching",
    "respiratory-teaching",
    "teaching-tooling",
  ])
}

resource "github_branch_protection" "main" {
  for_each = local.teaching_repos

  repository_id = each.value
  pattern       = "main"

  required_pull_request_reviews {
    required_approving_review_count = 0
  }

  required_status_checks {
    strict   = true
    contexts = ["Validate teaching content"]
  }

  enforce_admins = false
}

resource "github_branch_protection" "tooling_main" {
  repository_id = "teaching-tooling"
  pattern       = "main"

  required_pull_request_reviews {
    required_approving_review_count = 0
  }

  required_status_checks {
    strict   = true
    contexts = ["python-tests", "node-tests"]
  }

  enforce_admins = false
}

# Restrict branch names to main or feature/* on all teaching repos
resource "github_repository_ruleset" "branch_naming" {
  for_each = local.all_teaching_repos

  name        = "branch-naming"
  repository  = each.value
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~ALL"]
      exclude = []
    }
  }

  rules {
    branch_name_pattern {
      operator = "regex"
      pattern  = "^(main|feature/.+)$"
    }
  }
}
