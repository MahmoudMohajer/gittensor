import sys
import os
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gittensor.constants import PARETO_DISTRIBUTION_ALPHA_VALUE

def simulate_rewards():
    # Hypothetical scores based on user input and typical distribution
    scores = {
        "Top Miner": 44680.0,
        "Miner 2": 25000.0,
        "Miner 3": 15000.0,
        "Miner 4": 8000.0,
        "Miner 5": 4000.0,
        "Miner 6": 2000.0,
        "Miner 7": 1000.0,
        "Miner 8": 500.0,
        "Miner 9": 100.0,
        "Miner 10": 50.0,
    }
    
    # 1. Pareto Normalization
    alpha = PARETO_DISTRIBUTION_ALPHA_VALUE
    print(f"Applying Pareto (alpha={alpha})...")
    
    pareto_scores = {
        name: (score ** (1.0 / alpha)) 
        for name, score in scores.items()
    }
    
    total_pareto = sum(pareto_scores.values())
    normalized_rewards = {
        name: score / total_pareto 
        for name, score in pareto_scores.items()
    }
    
    # 2. Dynamic Emissions (Hypothetical Scalar)
    # Assuming network is healthy enough for 80% emissions
    emission_scalar = 0.80 
    
    print(f"{'Miner':<15} | {'Raw Score':<10} | {'Pareto Score':<12} | {'Share (%)':<10} | {'Est. Daily TAO':<15}")
    print("-" * 80)
    
    # Assuming ~7200 TAO/day total subnet emission (just an example number for context)
    # Actually, let's just show percentage share of the *active* pool
    
    for name, score in scores.items():
        share = normalized_rewards[name]
        # If total subnet emission is e.g. 100 TAO/day (arbitrary unit)
        # The miner gets: Share * Scalar * TotalEmission
        
        print(f"{name:<15} | {score:<10.0f} | {pareto_scores[name]:<12.0f} | {share*100:<10.2f}% | (depends on emission)")

if __name__ == "__main__":
    simulate_rewards()
