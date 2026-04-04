from datetime import datetime, timedelta


def format_number(n):
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}M'
    elif n >= 1_000:
        return f'{n/1_000:.1f}K'
    return str(n)


def truncate_text(text, max_len=4096):
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'


def progress_bar(current, total, length=10):
    if total == 0:
        return '\u2591' * length
    filled = int(current / total * length)
    return '\u2593' * filled + '\u2591' * (length - filled)


def time_ago(dt):
    if not dt:
        return 'Never'
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return str(dt)
    delta = datetime.now(dt.tzinfo) - dt
    if delta.days > 30:
        return f'{delta.days // 30} months ago'
    elif delta.days > 0:
        return f'{delta.days} days ago'
    elif delta.seconds > 3600:
        return f'{delta.seconds // 3600} hours ago'
    elif delta.seconds > 60:
        return f'{delta.seconds // 60} minutes ago'
    return 'Just now'


def format_duration(seconds):
    if seconds < 60:
        return f'{seconds}s'
    elif seconds < 3600:
        return f'{seconds // 60}m {seconds % 60}s'
    return f'{seconds // 3600}h {(seconds % 3600) // 60}m'
