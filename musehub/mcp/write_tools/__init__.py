"""Write tool executors — side-effecting MCP tool implementations.

Each sub-module handles a domain of write operations:
  repos     → create_repo, fork_repo
  issues    → create_issue, update_issue, create_issue_comment
  pulls     → create_pr, merge_pr, create_pr_comment, submit_pr_review
  releases  → create_release
  social    → star_repo, create_label

All public functions are async, accept plain scalar arguments extracted from
the MCP ``arguments`` dict, and return ``MusehubToolResult``.
"""
