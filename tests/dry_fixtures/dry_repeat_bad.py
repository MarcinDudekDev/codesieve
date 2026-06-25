"""Fixture: the same byte-math idiom repeated with DIFFERENT variable names."""


def summarize(alloc, used, freed):
    big = round(alloc / (1024 * 1024), 2)
    small = round(used / (1024 * 1024), 2)
    extra = round(freed / (1024 * 1024), 2)
    return big, small, extra
