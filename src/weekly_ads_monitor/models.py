from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"


@dataclass
class Metrics:
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    target_leads: int = 0
    non_target_leads: int = 0
    unprocessed_leads: int = 0
    unclassified_leads: int = 0

    def derived(self) -> dict[str, float | None]:
        return {
            "ctr": self.clicks / self.impressions if self.impressions else None,
            "cpc": self.spend / self.clicks if self.clicks else None,
            "cpa": self.spend / self.leads if self.leads else None,
            "cr": self.leads / self.clicks if self.clicks else None,
            "target_cpa": self.spend / self.target_leads if self.target_leads else None,
            "target_share": self.target_leads / self.leads if self.leads else None,
            "unprocessed_share": self.unprocessed_leads / self.leads if self.leads else None,
        }

