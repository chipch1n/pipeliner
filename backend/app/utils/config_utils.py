from os import getenv

def required_env(name):
    value = getenv(name)
    if value is None:
        raise Exception(f"Missing required env: {name}")
    else:
        return value