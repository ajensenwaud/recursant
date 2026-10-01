from .coerce import coerce
from .interp import interpolate
from .parse import parse_ini


def load_config(text, variables=None):
    variables = {} if variables is None else variables
    return {
        section: {key: coerce(interpolate(value, variables)) for key, value in items.items()}
        for section, items in parse_ini(text).items()
    }
