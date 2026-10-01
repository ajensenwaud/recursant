import json
from pathlib import Path
from .migrate import upgrade


class Store:
    """v2 JSON: {"version": 2, "accounts": {name: {"balance_cents": int, "currency": str}}, "log": [...]}"""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self.data = upgrade(raw)
            if self.data is not raw:
                self.save()
        else:
            self.data = {"version": 2, "accounts": {}, "log": []}

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))
