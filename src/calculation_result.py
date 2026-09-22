"""Only a completed worker may supply a reusable calculation result."""
import json
import uuid


def preserve_previous(output):
    """A retry must produce its own output; keep old files for inspection."""
    if output.exists():
        output.rename(output.with_name(output.name + '.previous-' + uuid.uuid4().hex))


def completed(output, attempt):
    if not output.is_file() or not attempt.is_file():
        return False
    try:
        state = json.loads(attempt.read_text(encoding='utf-8'))
        if state.get('stage') != 'completed':
            return False
        if output.suffix.lower() == '.json':
            return isinstance(json.loads(output.read_text(encoding='utf-8')), dict)
        return output.stat().st_size > 0
    except (OSError, ValueError, AttributeError):
        return False
