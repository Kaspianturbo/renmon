"""Bounded multi-DID reading; failure disables batching until reconnect/restart."""

import logging

from renmon.elm import ElmError

log = logging.getLogger(__name__)


class Performance:
    def __init__(self, lengths, enabled=False):
        self.lengths = lengths
        self.enabled = enabled
        self.validated = set()
        self.excluded = set()
        self.failed = False
        self.reason = ""
        self.requests = 0
        self.batched = False

    def snapshot(self):
        status = (
            "off"
            if not self.enabled
            else (
                "fallback"
                if self.failed
                else ("active" if self.batched else "checking")
            )
        )
        return dict(enabled=self.enabled, status=status, reason=self.reason)

    def read(self, elm, requests, stop=None):
        self.requests = 0
        self.batched = False
        payloads, errors = {}, {}
        eligible = [
            r
            for r in requests
            if self.enabled
            and not self.failed
            and r in self.validated
            and r not in self.excluded
        ]
        batches = [eligible[i : i + 3] for i in range(0, len(eligible), 3)]
        batches += [[r] for r in requests if r not in eligible]
        for batch in batches:
            if stop is not None and stop.is_set():
                break
            self.requests += 1
            try:
                if len(batch) > 1:
                    payload = elm.request_many(batch)
                    parts = split_response(payload, batch, self.lengths)
                    payloads.update(parts)
                    self.batched = True
                else:
                    r = batch[0]
                    payload = elm.request(r)
                    payloads[r] = payload
                    did = r[2:]
                    if self.enabled and did in self.lengths and int(did, 16) % 0x20:
                        if (
                            payload.startswith(bytes.fromhex("62" + did))
                            and len(payload) == self.lengths[did] + 3
                        ):
                            self.validated.add(r)
                        else:
                            self.excluded.add(r)
            except ElmError as exc:
                for r in batch:
                    errors[r] = str(exc)
                if len(batch) > 1:
                    log.warning(
                        "Performance fallback: requests=%s expected_lengths=%s exchange=%r reason=%s",
                        batch,
                        {r[2:]: self.lengths.get(r[2:]) for r in batch},
                        getattr(elm, "last_exchange", None),
                        exc,
                    )
                    self.failed = True
                    self.reason = str(exc)
                    # No immediate retries after a timeout/rejection. Next cycle uses singles.
                    for r in requests:
                        if r not in payloads:
                            errors.setdefault(
                                r,
                                "Performance вимкнено; окреме читання з наступного циклу",
                            )
                    break
        return payloads, errors


def split_response(payload, requests, lengths):
    if not payload.startswith(b"\x62"):
        raise ElmError("Performance: очікувалась відповідь 62")
    pos, result = 1, {}
    for request in requests:
        did = request[2:]
        end = pos + 2 + lengths[did]
        if end > len(payload) or payload[pos : pos + 2] != bytes.fromhex(did):
            raise ElmError(
                "Performance: неправильний DID, порядок або довжина відповіді"
            )
        result[request] = b"\x62" + payload[pos:end]
        pos = end
    if pos != len(payload):
        raise ElmError("Performance: зайві байти у відповіді")
    return result
