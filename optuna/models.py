from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyParams:
    """
    Integer parameters are stored in 0.001 units.

    Example:
        p1=10 -> 0.010
        thursday_open_stop=15 -> 0.015
    """

    p1: int
    p2: int
    p3: int
    p4: int
    p5: int

    thursday_stop: int
    friday_stop: int

    @property
    def tpps(self) -> list[float]:
        """
        Mapping from the five effective parameters:

        Monday:    p1, p1
        Tuesday:   p1, p2
        Wednesday: p2, p3
        Thursday:  p3, p4
        Friday:    p4, p5
        """
        return [
            self.p1 / 1000,
            self.p2 / 1000,
            self.p3 / 1000,
            self.p4 / 1000,
            self.p5 / 1000,
        ]

    @property
    def thursday_stop_fraction(self) -> float:
        return self.thursday_stop / 1000

    @property
    def friday_stop_fraction(self) -> float:
        return self.friday_stop / 1000

    def to_dict(self) -> dict:
        result = asdict(self)
        result["tpps"] = self.tpps
        return result

    @classmethod
    def from_optuna_params(cls, values: dict) -> "StrategyParams":
        return cls(
            p1=int(values["p1"]),
            p2=int(values["p2"]),
            p3=int(values["p3"]),
            p4=int(values["p4"]),
            p5=int(values["p5"]),
            thursday_stop=int(values["thursday_stop"]),
            friday_stop=int(values["friday_stop"])
        )