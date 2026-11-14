"""Prefixed opaque ids (contract §0): a type prefix, an underscore and 32 lowercase hex characters."""

import uuid

AGENT = "agt"
EXECUTION = "exe"
STEP = "stp"
EVENT = "evt"
ANOMALY = "anm"
INVESTIGATION = "inv"
REPLAY = "rpl"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
