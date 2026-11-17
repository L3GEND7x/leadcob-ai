from contextlib import nullcontext
from app.jobs.discover_contacts import process


class Stop:
    def __init__(self, limit=100):
        self.waits = []
        self.limit = limit

    def is_set(self):
        return len(self.waits) >= self.limit

    def wait(self, seconds):
        self.waits.append(seconds)


def test_bounded_worker():
    stop = Stop()
    assert process(stop, max_items=2, session_factory=lambda: nullcontext(None),
                   process_one=lambda db: True) == 2
    assert stop.waits == [2, 2]


def test_continuous_worker_waits_and_stops():
    stop = Stop(3)
    outcomes = iter([False, True, False])
    assert process(stop, continuous=True, session_factory=lambda: nullcontext(None),
                   process_one=lambda db: next(outcomes)) == 1
    assert stop.waits == [15, 2, 15]


def test_worker_retries_infrastructure_failure():
    stop = Stop(2)
    def fail(db):
        raise RuntimeError('fixture')
    assert process(stop, continuous=True, session_factory=lambda: nullcontext(None),
                   process_one=fail) == 0
    assert stop.waits == [15, 15]
