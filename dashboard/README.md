# Dashboard usage

The dashboard can consume the lightweight scoring API without running a full validator.

## Scoring API (Flask)
- Endpoint: `POST /score-pr` (default host `http://localhost:5100`)
- Payload:
  ```json
  {
    "repo_full_name": "owner/repo",
    "pr_number": 123,
    "github_token": "ghp_xxx",
    "total_open_prs": 0
  }
  ```
- Response includes base score, earned score, multipliers, additions/deletions, and file count.

Example:
```bash
curl -X POST http://localhost:5100/score-pr \
  -H "Content-Type: application/json" \
  -d '{"repo_full_name":"entrius/gittensor","pr_number":1,"github_token":"$GITHUB_TOKEN"}'
```

## Integrating from the dashboard service
Call the API instead of re-implementing scoring. In `dashboard/services/competitor_service.py`, fetch PRs as today, then for each PR make a request:

```python
import requests

resp = requests.post(
    "http://localhost:5100/score-pr",
    json={
        "repo_full_name": repo,
        "pr_number": pr_number,
        "github_token": token,
        "total_open_prs": 0,
    },
    timeout=20,
)
resp.raise_for_status()
score_payload = resp.json()
estimated_score = score_payload["score"]["earned"]
```

Set the API URL via an environment variable in production so the dashboard can point to the running scorer instance.

