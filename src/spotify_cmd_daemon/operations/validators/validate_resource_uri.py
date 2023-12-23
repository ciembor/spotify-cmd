import re

def validate_resource_uri(resource_uri):
    pattern = re.compile(r'^spotify:(track|album|playlist):[a-zA-Z0-9]+$')
    return bool(pattern.match(resource_uri))
