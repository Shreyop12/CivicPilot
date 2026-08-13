import json
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

DEFAULT_CROSSWALK_PATH = Path(__file__).parent / "data" / "agency_crosswalk.json"
FUZZY_THRESHOLD = 85


@dataclass(frozen=True)
class AgencyMapping:
    name: str
    fr_slug: str
    usaspending_toptier_code: str


@dataclass(frozen=True)
class AgencyResolution:
    matched_name: str
    fr_slug: str | None
    usaspending_toptier_code: str | None
    verified: bool


class AgencyCrosswalk:
    def __init__(self, mappings: list[AgencyMapping]):
        self._by_name = {m.name.lower(): m for m in mappings}

    def resolve(self, agency_query: str) -> AgencyResolution:
        key = agency_query.strip().lower()
        exact = self._by_name.get(key)
        if exact is not None:
            return AgencyResolution(
                matched_name=exact.name,
                fr_slug=exact.fr_slug,
                usaspending_toptier_code=exact.usaspending_toptier_code,
                verified=True,
            )

        candidates = list(self._by_name.keys())
        best = process.extractOne(key, candidates, scorer=fuzz.WRatio) if candidates else None
        if best is None or best[1] < FUZZY_THRESHOLD:
            return AgencyResolution(
                matched_name=agency_query,
                fr_slug=None,
                usaspending_toptier_code=None,
                verified=False,
            )

        match = self._by_name[best[0]]
        return AgencyResolution(
            matched_name=match.name,
            fr_slug=match.fr_slug,
            usaspending_toptier_code=match.usaspending_toptier_code,
            verified=False,
        )


def load_default_crosswalk(path: Path = DEFAULT_CROSSWALK_PATH) -> AgencyCrosswalk:
    raw = json.loads(path.read_text())
    mappings = [AgencyMapping(**entry) for entry in raw]
    return AgencyCrosswalk(mappings)
