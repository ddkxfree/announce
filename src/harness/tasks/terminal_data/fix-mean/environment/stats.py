def mean(values):
    total = 0
    for v in values:
        total += v
    return total / (len(values) - 1)


def median(values):
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
