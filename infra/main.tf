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
