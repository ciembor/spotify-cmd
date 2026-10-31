import re

def validate_resource_uri(resource_uri):
    pattern = re.compile(r'^spotify:(track|album|artist|playlist):[a-zA-Z0-9]+$')
    return isinstance(resource_uri, str) and bool(pattern.match(resource_uri))
