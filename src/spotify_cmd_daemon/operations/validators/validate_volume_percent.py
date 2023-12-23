def validate_volume_percent(value):
    ivalue = int(value)
    is_valid = True

    if ivalue < 0 or ivalue > 100:
        is_valid = False

    return is_valid
