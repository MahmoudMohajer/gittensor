"""
Lightweight Flask API to score a single GitHub pull request using existing
validator scoring logic without running the full validator loop.

POST /score-pr
{
  "repo_full_name": "owner/repo",
  "pr_number": 123,
  "github_token": "ghp_xxx",
  "total_open_prs": 0      # optional, for spam penalty multiplier
}

Response (200):
{
  "pr": {...},
  "score": {
    "base": 10.5,
    "earned": 21.0,
    "multipliers": {...}
  },
  "meta": {...}
}
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional, Tuple

import bittensor as bt
import requests
from flask import Flask, jsonify, request

from gittensor.classes import MinerEvaluation, PullRequest
from gittensor.constants import PR_TAGLINE
from gittensor.utils.github_api_tools import (
    get_github_id,
    get_pull_request_file_changes,
)
from gittensor.validator.evaluation.scoring import score_pull_requests
from gittensor.validator.utils.datetime_utils import parse_github_timestamp
from gittensor.validator.utils.load_weights import (
    load_master_repo_weights,
    load_programming_language_weights,
)

# Ensure project root on path when run directly (defensive; usually already on sys.path)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

app = Flask(__name__)
session = requests.Session()

# Load weights once at startup
MASTER_REPOSITORIES = load_master_repo_weights()
PROGRAMMING_LANGUAGES = load_programming_language_weights()


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _error(message: str, status: int = 400, details: Optional[Dict] = None):
    payload = {"error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def _fetch_pr_metadata(
    repo_full_name: str, pr_number: int, token: str
) -> Tuple[Optional[Dict], Optional[Tuple[dict, int]]]:
    """Fetch PR metadata from GitHub REST API."""
    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
    try:
        resp = session.get(url, headers=_headers(token), timeout=15)
    except requests.RequestException as exc:
        return None, ({"message": f"GitHub request failed: {exc}"}, 502)

    if resp.status_code == 404:
        return None, ({"message": "Pull request not found", "status": 404}, 404)
    if resp.status_code == 401:
        return None, ({"message": "Unauthorized GitHub token", "status": 401}, 401)
    if resp.status_code == 403:
        rate_reset = resp.headers.get("X-RateLimit-Reset")
        details = {"message": "GitHub rate limited", "status": 403}
        if rate_reset:
            details["rate_limit_reset"] = rate_reset
        return None, (details, 429)
    if resp.status_code >= 300:
        return None, (
            {"message": f"GitHub error {resp.status_code}", "status": resp.status_code},
            502,
        )

    return resp.json(), None


def _detect_tagline(body: str, merged_at, last_edited_at) -> bool:
    """Check if PR body ends with the expected Gittensor tagline."""
    if not body:
        return False
    description_end = body[-100:].strip()
    description_end_cleaned = description_end.rstrip(".,!?;: \t\n")
    if not description_end_cleaned.lower().endswith(PR_TAGLINE.lower()):
        return False
    # Only count if not edited after merge
    if last_edited_at and merged_at and last_edited_at > merged_at:
        bt.logging.warning(
            "Tagline present but PR edited after merge; ignoring tagline multiplier"
        )
        return False
    return True


def _build_pull_request(
    repo_full_name: str, pr_number: int, token: str, pr_data: Dict
) -> PullRequest:
    """Create PullRequest dataclass from GitHub REST payload."""
    merged_at_raw = pr_data.get("merged_at")
    if not merged_at_raw:
        raise ValueError("PR is not merged; only merged PRs are scored.")

    merged_at = parse_github_timestamp(merged_at_raw)
    created_at = parse_github_timestamp(pr_data["created_at"])
    last_edited_at = (
        parse_github_timestamp(pr_data["updated_at"])
        if pr_data.get("updated_at")
        else None
    )
    description = pr_data.get("body", "") or ""

    gittensor_tagged = _detect_tagline(description, merged_at, last_edited_at)

    pr = PullRequest(
        number=pr_number,
        repository_full_name=repo_full_name,
        uid=0,
        hotkey="manual",
        github_id=str(pr_data.get("user", {}).get("id", "")),
        title=pr_data.get("title", ""),
        author_login=pr_data.get("user", {}).get("login", ""),
        merged_at=merged_at,
        created_at=created_at,
        additions=pr_data.get("additions", 0),
        deletions=pr_data.get("deletions", 0),
        commits=pr_data.get("commits", 0),
        merged_by_login=pr_data.get("merged_by", {}).get("login")
        if pr_data.get("merged_by")
        else None,
        description=description,
        last_edited_at=last_edited_at,
        gittensor_tagged=gittensor_tagged,
        issues=[],
    )
    return pr


def _serialize_pr(pr: PullRequest) -> Dict:
    multipliers = {
        "repo_weight_multiplier": pr.repo_weight_multiplier,
        "issue_multiplier": pr.issue_multiplier,
        "open_pr_spam_multiplier": pr.open_pr_spam_multiplier,
        "repository_uniqueness_multiplier": pr.repository_uniqueness_multiplier,
        "time_decay_multiplier": pr.time_decay_multiplier,
        "gittensor_tag_multiplier": pr.gittensor_tag_multiplier,
        "merge_success_multiplier": pr.merge_success_multiplier,
    }

    return {
        "number": pr.number,
        "repo": pr.repository_full_name,
        "title": pr.title,
        "author": pr.author_login,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "total_lines_scored": pr.total_lines_scored,
        "file_count": len(pr.file_changes or []),
        "gittensor_tagged": pr.gittensor_tagged,
        "multipliers": multipliers,
        "base_score": pr.base_score,
        "earned_score": pr.earned_score,
    }


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "repositories": len(MASTER_REPOSITORIES),
            "languages": len(PROGRAMMING_LANGUAGES),
        }
    )


@app.route("/score-pr", methods=["POST"])
def score_pr():
    data = request.get_json(silent=True) or {}
    repo_full_name = data.get("repo_full_name") or data.get("repo")
    pr_number = data.get("pr_number")
    token = data.get("github_token") or data.get("token")
    total_open_prs = data.get("total_open_prs", 0)

    if not repo_full_name or not pr_number or not token:
        return _error("repo_full_name, pr_number, and github_token are required.", 400)

    try:
        pr_number = int(pr_number)
    except ValueError:
        return _error("pr_number must be an integer.", 400)

    try:
        total_open_prs = int(total_open_prs)
    except (TypeError, ValueError):
        total_open_prs = 0

    pr_data, err = _fetch_pr_metadata(repo_full_name, pr_number, token)
    if err:
        return jsonify(err[0]), err[1]

    try:
        pr = _build_pull_request(repo_full_name, pr_number, token, pr_data)
    except ValueError as exc:
        return _error(str(exc), 400)

    # Fetch file changes
    pr_file_changes = get_pull_request_file_changes(repo_full_name, pr_number, token)
    if not pr_file_changes:
        return _error("No file changes returned for this PR.", 404)

    pr.set_file_changes(pr_file_changes)

    # Build miner evaluation shell
    github_id = pr.github_id or get_github_id(token) or "0"
    miner_eval = MinerEvaluation(
        uid=0,
        hotkey="manual",
        github_id=github_id,
        github_pat=token,
        total_open_prs=total_open_prs or 0,
        total_closed_prs=0,
        total_merged_prs=1,
    )
    miner_eval.add_pull_request(pr)

    # Score (base + multipliers)
    score_pull_requests(miner_eval, MASTER_REPOSITORIES, PROGRAMMING_LANGUAGES)

    # Finalize earned scores (no cross-miner uniqueness applied here, keep multiplier at 1.0)
    for scored_pr in miner_eval.pull_requests:
        scored_pr.repository_uniqueness_multiplier = 1.0
        scored_pr.calculate_final_earned_score()
        miner_eval.base_total_score += scored_pr.base_score
        miner_eval.total_score += scored_pr.earned_score
        miner_eval.total_lines_changed += scored_pr.total_lines_scored
        miner_eval.unique_repos_contributed_to.add(scored_pr.repository_full_name)
    miner_eval.unique_repos_count = len(miner_eval.unique_repos_contributed_to)

    response = {
        "pr": _serialize_pr(pr),
        "miner": {
            "github_id": miner_eval.github_id,
            "total_open_prs": miner_eval.total_open_prs,
        },
        "score": {
            "base": pr.base_score,
            "earned": pr.earned_score,
            "multipliers": _serialize_pr(pr)["multipliers"],
        },
        "meta": {
            "repo_weight_source": "gittensor/validator/weights/master_repositories.json",
            "language_weight_source": "gittensor/validator/weights/programming_languages.json",
        },
    }
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100)
