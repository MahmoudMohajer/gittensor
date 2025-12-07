import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gittensor.classes import PullRequest, FileChange
from gittensor.validator.utils.load_weights import load_programming_language_weights

def create_dummy_pr(file_changes):
    return PullRequest(
        number=1,
        repository_full_name="test/repo",
        uid=1,
        hotkey="test_hotkey",
        github_id="test_github_id",
        title="Test PR",
        author_login="test_user",
        merged_at=datetime.now(),
        created_at=datetime.now(),
        file_changes=file_changes
    )

def run_analytics():
    print("Loading language weights...")
    weights = load_programming_language_weights()
    
    def get_base_files():
        return [FileChange(1, "test/repo", "main.py", 100, 100, 0, "modified", patch="+print('hello world')\n" * 100)]
    
    def get_cpp_files():
        return [FileChange(1, "test/repo", "core.cpp", 100, 100, 0, "modified", patch="+int x = 1;\n" * 100)]

    TARGET_SCORE = 44679.93
    print(f"Target Score to Beat: {TARGET_SCORE:,.2f}")
    print("-" * 100)

    scenarios = [
        {
            "name": "1. The 'One Shot' (Maxed)",
            "files_func": get_base_files, # 100 lines Python
            "repo_weight": 59.34,
            "issue_bonus": 2.8,   # Max for 2 issues (1.0 + 0.9 + 0.9)
            "tagline": 2.0,
            "desc": "1 PR: High Repo + Tagline + 2 Old Issues"
        },
        {
            "name": "2. The 'Realistic' Winner",
            "files_func": get_base_files, # 100 lines Python
            "repo_weight": 59.34,
            "issue_bonus": 1.9,   # 1 Old Issue (1.0 + 0.9)
            "tagline": 2.0,
            "desc": "1 PR: High Repo + Tagline + 1 Old Issue"
        },
        {
            "name": "3. The 'Grinder' (No Issues)",
            "files_func": get_base_files, # 100 lines Python
            "repo_weight": 59.34,
            "issue_bonus": 1.0,   # No issues
            "tagline": 2.0,
            "desc": "High Repo + Tagline (Needs multiple PRs)"
        }
    ]

    print(f"{'Scenario':<30} | {'Base':<8} | {'Mults':<20} | {'Score':<10} | {'Vs Target'}")
    print("-" * 100)

    for i, scenario in enumerate(scenarios):
        pr = create_dummy_pr(scenario['files_func']())
        
        # 1. Calculate Base Score
        pr.base_score = pr.calculate_score_from_file_changes(weights)
        
        # 2. Apply Multipliers
        pr.repo_weight_multiplier = scenario['repo_weight']
        pr.issue_multiplier = scenario['issue_bonus']
        pr.gittensor_tag_multiplier = scenario['tagline']
        
        # Calculate Final Score
        final_score = pr.calculate_final_earned_score()
        
        # Calculate how many PRs needed to win
        prs_needed = 1
        if final_score < TARGET_SCORE:
            import math
            prs_needed = math.ceil(TARGET_SCORE / final_score)
            status = f"Needs {prs_needed} PRs"
        else:
            status = "WINS in 1 PR!"

        # Format multipliers string
        mults = f"R:{scenario['repo_weight']:.1f} I:{scenario['issue_bonus']:.1f} T:{scenario['tagline']:.1f}"
        
        print(f"{scenario['name']:<30} | {pr.base_score:<8.1f} | {mults:<20} | {final_score:<10.0f} | {status}")

if __name__ == "__main__":
    run_analytics()
