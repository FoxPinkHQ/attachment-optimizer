def human_size(size):
    if not size:
        return "0 B"
    if size < 1024:
        return f"{size} B"
    if size < 1024 ** 2:
        return f"{round(size / 1024, 1)} KB"
    if size < 1024 ** 3:
        return f"{round(size / 1024 ** 2, 1)} MB"
    return f"{round(size / 1024 ** 3, 1)} GB"
