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

def fetch_issues(token, repos):
    url = "https://api.github.com/graphql"
    headers = {"Authorization": f"Bearer {token}"}
    
    # Calculate cutoff date (45 days ago)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=45)
    cutoff_iso = cutoff_date.isoformat()
    
    print(f"Fetching issues created before {cutoff_iso}...")
    
    all_issues = []
    
    # Process in batches to avoid query complexity limits
    batch_size = 10
    repo_names = list(repos.keys())
    
    for i in range(0, len(repo_names), batch_size):
        batch = repo_names[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{len(repo_names)//batch_size + 1}...")
        
        # Construct dynamic query alias for each repo
        query_parts = []
        for idx, repo_full_name in enumerate(batch):
            owner, name = repo_full_name.split('/')
            # GraphQL alias must be alphanumeric
            alias = f"repo_{idx}"
            query_parts.append(f"""
            {alias}: repository(owner: "{owner}", name: "{name}") {{
                nameWithOwner
                issues(states: OPEN, first: 20, orderBy: {{field: CREATED_AT, direction: ASC}}) {{
                    nodes {{
                        title
                        number
                        url
                        createdAt
                        author {{
                            login
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
                    
                    # Double check age (though we sorted by ASC, we only took first 20)
                    age_days = (datetime.now(timezone.utc) - created_at).days
                    
                    if age_days >= 45:
                        all_issues.append({
                            "repo": repo_full_name,
                            "weight": weight,
                            "title": issue['title'],
                            "number": issue['number'],
                            "url": issue['url'],
                            "age": age_days,
                            "created_at": issue['createdAt'],
                            "author": issue['author']['login'] if issue.get('author') else "Unknown"
                        })
                        
        except Exception as e:
            print(f"Exception fetching batch: {e}")
            
        time.sleep(1) # Rate limit niceness

    return all_issues

def main():
    token = get_token()
    print("Loading master repositories...")
    all_repos = load_master_repo_weights()
    
    # Filter for active and high weight repos (> 1.0 weight) to save time/API calls
    # Or just top 50 by weight
    active_repos = {k: v for k, v in all_repos.items() if v.get('inactiveAt') is None}
    sorted_repos = sorted(active_repos.items(), key=lambda x: x[1]['weight'], reverse=True)
    top_repos = dict(sorted_repos[:50]) # Top 50 repos
    
    print(f"Scanning top {len(top_repos)} repositories for aged issues...")
    
    issues = fetch_issues(token, top_repos)
    
    # Sort by weight desc, then age desc
    issues.sort(key=lambda x: (x['weight'], x['age']), reverse=True)
    
    output_dir = os.path.join(os.path.dirname(__file__), '../dashboard')
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, 'data.json')
    with open(output_file, 'w') as f:
        json.dump({"updated_at": datetime.now().isoformat(), "issues": issues}, f, indent=2)
        
    print(f"Found {len(issues)} aged issues. Saved to {output_file}")

if __name__ == "__main__":
    main()
