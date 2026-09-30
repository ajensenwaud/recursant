import json
from pathlib import Path


class Store:
    """JSON file: {"accounts": {name: {"balance": float}}, "log": [[kind, name, amount, balance], ...]}"""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {"accounts": {}, "log": []}

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))
