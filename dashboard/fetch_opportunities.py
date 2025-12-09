import os
import sys
import json
import requests
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gittensor.validator.utils.load_weights import load_master_repo_weights

# Load env from miner directory
load_dotenv(os.path.join(os.path.dirname(__file__), '../gittensor/miner/.env'))

def get_token():
    token = os.getenv('GITTENSOR_MINER_PAT')
    if not token:
        print("Error: GITTENSOR_MINER_PAT not found in .env")
        sys.exit(1)
    return token

def estimate_difficulty(title, labels):
    title_lower = title.lower()
    label_names = [l['name'].lower() for l in labels]
    
    # Easy signals
    easy_keywords = ['typo', 'doc', 'readme', 'comment', 'rename', 'fix link']
    easy_labels = ['good first issue', 'documentation', 'easy', 'help wanted', 'good-first-issue']
    
    if any(k in title_lower for k in easy_keywords) or any(l in label_names for l in easy_labels):
        return "Easy"
        
    # Hard signals
    hard_keywords = ['rewrite', 'refactor', 'architect', 'performance', 'memory', 'leak', 'security', 'c++']
    hard_labels = ['enhancement', 'feature', 'refactor', 'performance', 'security', 'complex']
    
    if any(k in title_lower for k in hard_keywords) or any(l in label_names for l in hard_labels):
        return "Hard"
        
    return "Medium"

import sqlite3

# ... (imports remain)

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS issues (
            id TEXT PRIMARY KEY,
            repo TEXT,
            weight REAL,
            title TEXT,
            number INTEGER,
            url TEXT,
            age INTEGER,
            created_at TEXT,
            author TEXT,
            labels TEXT,
            difficulty TEXT
        )
    ''')
    conn.commit()
    return conn

def fetch_issues(token, repos, db_conn):
    url = "https://api.github.com/graphql"
    headers = {"Authorization": f"Bearer {token}"}
    
    print("Fetching ALL open issues (no age limit)...")
    
    batch_size = 10
    repo_names = list(repos.keys())
    total_fetched = 0
    
    cursor = db_conn.cursor()
    
    for i in range(0, len(repo_names), batch_size):
        batch = repo_names[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{len(repo_names)//batch_size + 1}...")
        
        query_parts = []
        for idx, repo_full_name in enumerate(batch):
            owner, name = repo_full_name.split('/')
            alias = f"repo_{idx}"
            # Ordered by Created At ASC to get oldest issues first
            query_parts.append(f"""
            {alias}: repository(owner: "{owner}", name: "{name}") {{
                nameWithOwner
                issues(states: OPEN, first: 50, orderBy: {{field: CREATED_AT, direction: ASC}}) {{
                    nodes {{
                        title
                        number
                        url
                        createdAt
                        author {{
                            login
                        }}
                        labels(first: 5) {{
                            nodes {{
                                name
                            }}
                        }}
                    }}
                }}
            }}
            """)
            
        query = "query {" + "".join(query_parts) + "}"
        
        try:
            response = requests.post(url, json={"query": query}, headers=headers)
            if response.status_code != 200:
                print(f"Error: {response.status_code} - {response.text}")
                continue
                
            data = response.json()
            if 'errors' in data:
                print(f"GraphQL Errors: {data['errors']}")
                continue
                
            results = data.get('data', {})
            if not results:
                continue

            for idx, repo_full_name in enumerate(batch):
                alias = f"repo_{idx}"
                repo_data = results.get(alias)
                if not repo_data:
                    continue
                    
                issues = repo_data.get('issues', {}).get('nodes', [])
                weight = repos[repo_full_name].get('weight', 0)
                
                for issue in issues:
                    created_at = datetime.fromisoformat(issue['createdAt'].rstrip('Z')).replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - created_at).days
                    
                    labels_data = issue.get('labels', {}).get('nodes', [])
                    difficulty = estimate_difficulty(issue['title'], labels_data)
                    labels_json = json.dumps([l['name'] for l in labels_data])
                    
                    # Use URL as unique ID or repo+number
                    issue_id = f"{repo_full_name}#{issue['number']}"
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO issues 
                        (id, repo, weight, title, number, url, age, created_at, author, labels, difficulty)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        issue_id, repo_full_name, weight, issue['title'], issue['number'], 
                        issue['url'], age_days, issue['createdAt'], 
                        issue['author']['login'] if issue.get('author') else "Unknown",
                        labels_json, difficulty
                    ))
                    total_fetched += 1
            
            db_conn.commit()
                        
        except Exception as e:
            print(f"Exception fetching batch: {e}")
            
        time.sleep(1) 

    return total_fetched

def main():
    token = get_token()
    print("Loading master repositories...")
    all_repos = load_master_repo_weights()
    
    active_repos = {k: v for k, v in all_repos.items() if v.get('inactiveAt') is None}
    sorted_repos = sorted(active_repos.items(), key=lambda x: x[1]['weight'], reverse=True)
    top_repos = dict(sorted_repos[:50]) 
    
    print(f"Scanning top {len(top_repos)} repositories...")
    
    db_path = os.path.join(os.path.dirname(__file__), '../dashboard/opportunities.db')
    conn = init_db(db_path)
    
    count = fetch_issues(token, top_repos, conn)
    conn.close()
        
    print(f"Sync complete. {count} issues stored in {db_path}")

if __name__ == "__main__":
    main()
