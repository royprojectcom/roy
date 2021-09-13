import os

from roy.utils.collections import update_dict_recur


def _convert_value(value):
    """Convert value from env to python equvalent."""
    if value == 'false':
        value = False
    elif value == 'true':
        value = True
    elif value.isdigit():
        value = int(value)
    return value


def create_settings(settings: dict = None, update_with: dict = None):
    """Create app settings dict, overrided by env."""
    settings = settings or {}
    if update_with:
        settings = update_dict_recur(settings, update_with)

    for key, value in os.environ.items():
        if 'SETTINGS_' not in key:
            continue
        current_settings = settings
        parts = [
            part.lower()
            for part in key.replace('SETTINGS_', '').split('_')
        ]
        last_index = len(parts) - 1
        for index, part in enumerate(parts):
            if index == last_index:
                current_settings[part] = _convert_value(value)
            else:
                current_settings = current_settings.setdefault(part, {})
    return settings
