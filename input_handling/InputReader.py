class InputReader:
    def __init__(self) -> None:
        self.mapping: dict[str,str] = {}

    def setMapping(self, mapping: dict | None = None) -> None:
        if mapping is None:
            mapping = {}
        self.mapping.update(mapping)

    def parseInput(self, input) -> str:
        return self.mapping.get(input, "")
