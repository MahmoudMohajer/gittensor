def __getattr__(name):
    if name == "forward":
        from .forward import forward
        return forward
    if name == "reward":
        from .evaluation.reward import reward
        return reward
    raise AttributeError(f"module 'gittensor.validator' has no attribute '{name}'")
