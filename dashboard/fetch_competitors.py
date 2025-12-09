#!/usr/bin/env python3
"""
Fetch open PRs containing the Gittensor tagline to track competitors.
Uses GitHub Search API and calculates estimated scores.
"""
import os
import sys
import json
import sqlite3
import requests
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

def get_token():
    token = os.environ.get("GITTENSOR_MINER_PAT")
    if not token:
        print("Error: GITTENSOR_MINER_PAT environment variable not set")
        sys.exit(1)
    return token

def load_weights():
    """Load language and repo weights from the validator files."""
    script_dir = os.path.dirname(__file__)
    
    # Language weights
    lang_path = os.path.join(script_dir, '../gittensor/validator/weights/programming_languages.json')
    try:
        with open(lang_path, 'r') as f:
            lang_weights = json.load(f)
    except:
        lang_weights = {}
    
    # Repo weights
    repo_path = os.path.join(script_dir, '../gittensor/validator/weights/master_repositories.json')
    try:
        with open(repo_path, 'r') as f:
            repo_data = json.load(f)
            repo_weights = {r['repo']: r.get('weight', 1.0) for r in repo_data}
    except:
        repo_weights = {}
    
    return lang_weights, repo_weights

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

def calculate_pr_score(files, repo, lang_weights, repo_weights):
    """
    Calculate estimated score for a PR based on file changes.
    Uses the same logic as the validator.
    """
    # Constants from gittensor/constants.py
    DEFAULT_LANG_WEIGHT = 0.12
    TEST_FILE_WEIGHT = 0.10
    MITIGATED_EXTENSIONS = ["md", "txt", "json"]
    MAX_LINES_MITIGATED = 300
    TAGLINE_BOOST = 2.0
    GITTENSOR_REPO = "entrius/gittensor"
    
    base_score = 0.0
    
    for f in files:
        filename = f.get('filename', '').lower()
        additions = f.get('additions', 0)
        
        # Get file extension
        ext = os.path.splitext(filename)[1].lstrip('.')
        
        # Get language weight (default 0.12 for unknown extensions)
        lang_weight = lang_weights.get(ext, DEFAULT_LANG_WEIGHT)
        
        # Apply mitigated extension cap (md, txt, json capped at 300 lines)
        if ext in MITIGATED_EXTENSIONS:
            additions = min(additions, MAX_LINES_MITIGATED)
        
        # Check if it's a test file (reduced weight)
        is_test_file = 'test' in filename or 'spec' in filename or filename.startswith('test_')
        file_weight = TEST_FILE_WEIGHT if is_test_file else 1.0
        
        # Score: additions * language_weight * file_weight
        file_score = additions * lang_weight * file_weight
        base_score += file_score
    
    # Apply repo weight (default 1.0 for non-incentivized repos)
    repo_weight = repo_weights.get(repo, 1.0)
    
    # Apply tagline multiplier (2.0) for non-gittensor repos
    # PRs on gittensor repo itself don't get the bonus
    tagline_multiplier = TAGLINE_BOOST if repo.lower() != GITTENSOR_REPO.lower() else 1.0
    
    # Final estimated score
    estimated_score = base_score * repo_weight * tagline_multiplier
    
    return round(estimated_score, 2)

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
                files = get_pr_files(token, repo, pr_number)
                additions = sum(f.get('additions', 0) for f in files)
                deletions = sum(f.get('deletions', 0) for f in files)
                
                # Calculate estimated score
                estimated_score = calculate_pr_score(files, repo, lang_weights, repo_weights)
                
                print(f"  {pr_id}: +{additions}/-{deletions} -> ~{estimated_score} pts")
                
                cursor.execute('''
                    INSERT OR REPLACE INTO prs 
                    (id, repo, author, title, number, url, created_at, updated_at, state, age, additions, deletions, estimated_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pr_id,
                    repo,
                    item['user']['login'] if item.get('user') else 'Unknown',
                    item['title'],
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
            break
    
    return total_fetched

def main():
    token = get_token()
    
    print("Loading weights...")
    lang_weights, repo_weights = load_weights()
    
    db_path = os.path.join(os.path.dirname(__file__), '../dashboard/opportunities.db')
    conn = init_db(db_path)
    
    count = fetch_gittensor_prs(token, conn, lang_weights, repo_weights)
    conn.close()
    
    print(f"Sync complete. {count} competitor PRs stored with estimated scores.")

if __name__ == "__main__":
    main()
