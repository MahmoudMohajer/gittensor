
import os
import sys
import requests
import time
from datetime import datetime, timezone
import traceback

# Add project root to path to import gittensor modules
current_dir = os.path.dirname(os.path.abspath(__file__))
# dashboard/services -> dashboard -> gittensor (root)
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from gittensor.classes import PullRequest, FileChange

SCORING_API_URL = os.getenv("SCORING_API_URL", "http://localhost:5100/score-pr")

def get_pr_files(token, repo, pr_number):
    """Fetch file changes for a specific PR."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

def fetch_gittensor_prs(token, db_conn, lang_weights, repo_weights):
    """
    Use GitHub Search API to find open PRs with the Gittensor tagline.
    Scores them using the validator logic and updates the database.
    """
    url = "https://api.github.com/search/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    query = '"Contribution by Gittensor" is:pr is:open is:unmerged'
    
    params = {
        "q": query,
        "sort": "updated",
        "order": "desc",
        "per_page": 100
    }
    
    
    cursor = db_conn.cursor()
    # Flush existing data to remove stale/closed PRs
    print("Flushing existing PR data...")
    cursor.execute('DELETE FROM prs')
    db_conn.commit()

    print(f"Searching for PRs with Gittensor tagline...")
    
    total_fetched = 0
    page = 1
    
    TAGLINE_BOOST = 2.0
    GITTENSOR_REPO = "entrius/gittensor"

    while True:
        params["page"] = page
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 403:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - int(time.time()), 60)
                print(f"Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            if response.status_code != 200:
                print(f"Error: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            items = data.get('items', [])
            
            if not items:
                break
                
            print(f"Processing page {page} ({len(items)} PRs)...")
            
            for item in items:
                repo_url = item.get('repository_url', '')
                repo = '/'.join(repo_url.split('/')[-2:]) if repo_url else 'Unknown'
                
                created_at = item.get('created_at', '')
                created_dt = datetime.fromisoformat(created_at.rstrip('Z')).replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - created_dt).days
                
                pr_number = item['number']
                pr_id = f"{repo}#{pr_number}"
                
                # Fetch file changes for this PR
                raw_files = get_pr_files(token, repo, pr_number)
                
                # Convert to FileChange objects
                file_changes = []
                for rf in raw_files:
                    try:
                        file_changes.append(FileChange.from_github_response(pr_number, repo, rf))
                    except Exception as e:
                        print(f"Error parsing file change: {e}")

                additions = sum(f.additions for f in file_changes)
                deletions = sum(f.deletions for f in file_changes)
                
                # Construct PullRequest object for scoring
                pr = PullRequest(
                    number=pr_number,
                    repository_full_name=repo,
                    uid=0,
                    hotkey="none",
                    github_id="none",
                    title=item['title'],
                    author_login=item['user']['login'] if item.get('user') else 'Unknown',
                    merged_at=datetime.now(timezone.utc), # Dummy
                    created_at=created_dt,
                    file_changes=file_changes
                )

                # Calculate score via validator scoring API for consistency
                estimated_score = pr.base_score = pr.repo_weight_multiplier = pr.gittensor_tag_multiplier = 0.0
                try:
                    api_resp = requests.post(
                        SCORING_API_URL,
                        json={
                            "repo_full_name": repo,
                            "pr_number": pr_number,
                            "github_token": token,
                            "total_open_prs": 0,
                        },
                        timeout=20,
                    )
                    if api_resp.status_code == 200:
                        api_json = api_resp.json()
                        pr_data = api_json.get("pr", {})
                        score_data = api_json.get("score", {})

                        pr.base_score = pr_data.get("base_score", 0.0)
                        pr.repo_weight_multiplier = pr_data.get("multipliers", {}).get("repo_weight_multiplier", 1.0)
                        pr.gittensor_tag_multiplier = pr_data.get("multipliers", {}).get("gittensor_tag_multiplier", 1.0)
                        estimated_score = score_data.get("earned", pr.calculate_final_earned_score())
                    else:
                        print(f"Scoring API error {api_resp.status_code}: {api_resp.text}")
                        estimated_score = pr.calculate_final_earned_score()
                except Exception as e:
                    print(f"Scoring API call failed: {e}")
                    estimated_score = pr.calculate_final_earned_score()
                
                print(f"  {pr_id}: +{additions}/-{deletions} -> ~{estimated_score:.2f} pts")
                
                cursor.execute('''
                    INSERT OR REPLACE INTO prs 
                    (id, repo, author, title, number, url, created_at, updated_at, state, age, additions, deletions, estimated_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pr_id,
                    repo,
                    pr.author_login,
                    pr.title,
                    pr_number,
                    item['html_url'],
                    item['created_at'],
                    item['updated_at'],
                    item['state'],
                    age_days,
                    additions,
                    deletions,
                    estimated_score
                ))
                total_fetched += 1
                
                time.sleep(0.5)  # Be nice to the API
            
            db_conn.commit()
            
            if len(items) < 100:
                break
                
            page += 1
            time.sleep(2)
            
        except Exception as e:
            print(f"Error fetching PRs: {e}")
            traceback.print_exc()
            break
    
    return total_fetched
