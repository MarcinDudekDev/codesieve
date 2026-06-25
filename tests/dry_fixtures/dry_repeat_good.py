"""Counter-fixture: the repeated idiom factored into a single named helper."""


def to_megabytes(num_bytes):
    return round(num_bytes / (1024 * 1024), 2)


def summarize(alloc, used, freed):
    return to_megabytes(alloc), to_megabytes(used), to_megabytes(freed)
