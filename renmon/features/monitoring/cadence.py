"""Tick-based scheduling at DID granularity; never queues missed polls."""

DIVISORS = (1, 2, 3, 5, 10)


def divisor(value):
    if type(value) is not int or value not in DIVISORS:
        raise ValueError("Частота має бути 1, 2, 3, 5 або 10 циклів")
    return value


def divisors(value, codes):
    if not isinstance(value, dict) or any(code not in codes for code in value):
        raise ValueError("Некоректні частоти параметрів")
    return {code: divisor(value.get(code, 1)) for code in codes}


class Cadence:
    def __init__(self):
        self.tick = 0
        self.last = {}
        self.config = {}

    def due(self, signals, modifiers):
        groups = {}
        for signal in signals:
            groups.setdefault(signal.request, []).append(signal)
        config = {
            request: (
                min(modifiers.get(s.code, 1) for s in group),
                tuple(s.code for s in group),
            )
            for request, group in groups.items()
        }
        self.last = {
            r: t for r, t in self.last.items() if config.get(r) == self.config.get(r)
        }
        self.config = config
        return [
            s
            for r, group in groups.items()
            if r not in self.last or self.tick - self.last[r] >= config[r][0]
            for s in group
        ]

    def advance(self, signals):
        for signal in signals:
            self.last[signal.request] = self.tick
        self.tick += 1
