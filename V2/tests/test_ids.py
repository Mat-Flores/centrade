import time
from uuid import UUID

from centrade_core.ids import uuid7


def test_uuid7_has_correct_version_variant_and_timestamp() -> None:
    before = int(time.time() * 1000)
    u = uuid7()
    assert isinstance(u, UUID)
    assert u.version == 7
    assert u.variant == "specified in RFC 4122"
    assert before <= u.int >> 80 <= int(time.time() * 1000)


def test_uuid7_is_ordered_by_time_and_unique() -> None:
    a = uuid7()
    time.sleep(0.002)
    b = uuid7()
    assert a < b
    assert len({uuid7() for _ in range(1000)}) == 1000
