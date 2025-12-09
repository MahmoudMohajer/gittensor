#!/usr/bin/env python3
"""
Fetch open PRs containing the Gittensor tagline to track competitors.
Uses GitHub Search API and calculates estimated scores using the real validator logic.
"""
import os
import sys
import json
import sqlite3
import requests
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path to import gittensor modules
# Assumes this script is in /dashboard/ and gittensor package is in /gittensor/
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from gittensor.classes import PullRequest, FileChange
from gittensor.validator.utils.load_weights import load_programming_language_weights, load_master_repo_weights

load_dotenv()

def get_token():
    token = os.environ.get("GITTENSOR_MINER_PAT")
    if not token:
        print("Error: GITTENSOR_MINER_PAT environment variable not set")
        sys.exit(1)
    return token

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
    except:
        pass
    return []

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS prs (
            id TEXT PRIMARY KEY,
            repo TEXT,
            author TEXT,
            title TEXT,
            number INTEGER,
            url TEXT,
            created_at TEXT,
            updated_at TEXT,
            state TEXT,
            age INTEGER,
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            estimated_score REAL DEFAULT 0
        )
    ''')
    conn.commit()
    return conn

def fetch_gittensor_prs(token, db_conn, lang_weights, repo_weights):
    """
    Use GitHub Search API to find open PRs with the Gittensor tagline.
    """
    url = "https://api.github.com/search/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    query = '"Contribution by Gittensor" is:pr is:open'
    
    params = {
        "q": query,
        "sort": "updated",
        "order": "desc",
        "per_page": 100
    }
    
    print(f"Searching for PRs with Gittensor tagline...")
    
    cursor = db_conn.cursor()
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
                # Use dummy values for fields we don't need for scoring calculation or don't have
                pr = PullRequest(
                    number=pr_number,
                    repository_full_name=repo,
                    uid=0,
                    hotkey="none",
                    github_id="none",
                    title=item['title'],
                    author_login=item['user']['login'] if item.get('user') else 'Unknown',
                    merged_at=datetime.now(timezone.utc), # Dummy, not used in score calc logic for open PRs usually
                    created_at=created_dt,
                    file_changes=file_changes
                )

                # 1. Calculate Base Score
                pr.base_score = pr.calculate_score_from_file_changes(lang_weights)

                # 2. Apply Multipliers
                # Repo weight
                r_weight = 1.0
                if repo in repo_weights:
                    r_weight = repo_weights[repo].get('weight', 1.0)
                
                # Tagline multiplier
                tagline_multiplier = TAGLINE_BOOST if repo.lower() != GITTENSOR_REPO.lower() else 1.0
                
                pr.repo_weight_multiplier = r_weight
                pr.gittensor_tag_multiplier = tagline_multiplier
                # Other multipliers remain default (1.0) for estimation
                
                # 3. Calculate Final Score
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
            import traceback
            traceback.print_exc()
            break
    
    return total_fetched

def main():
    token = get_token()
    
    print("Loading weights...")
    lang_weights = load_programming_language_weights()
    repo_weights = load_master_repo_weights()
    
    db_path = os.path.join(os.path.dirname(__file__), '../dashboard/opportunities.db')
    conn = init_db(db_path)
    
    count = fetch_gittensor_prs(token, conn, lang_weights, repo_weights)
    conn.close()
    
    print(f"Sync complete. {count} competitor PRs stored with estimated scores.")

if __name__ == "__main__":
    main()
