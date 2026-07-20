def approx_tokens(*texts: str) -> int:
    return sum(len(t) for t in texts) // 4
