"""Safety checks for decoded JSON shared by HTTP requests and file inspection."""

MAX_JSON_NESTING_DEPTH = 100


def has_excessive_json_nesting(value: object) -> bool:
    pending = [(value, 0)]
    while pending:
        current, parent_depth = pending.pop()
        if isinstance(current, dict):
            children = current.values()
        elif isinstance(current, list):
            children = current
        else:
            continue

        depth = parent_depth + 1
        if depth > MAX_JSON_NESTING_DEPTH:
            return True
        pending.extend((child, depth) for child in children if isinstance(child, (dict, list)))
    return False
