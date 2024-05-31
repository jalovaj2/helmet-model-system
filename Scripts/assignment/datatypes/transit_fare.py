from __future__ import annotations
from typing import Any, Dict, Set, Union
import pandas


class TransitFareZoneSpecification:
    def __init__(self, fare_table: pandas.DataFrame):
        """Transit fare zone specification.

        Parameters
        ----------
        fare_table : pandas.DataFrame
            Table of transit zone combination fares
        """

        if 'dist' not in fare_table.columns:
            fare_table["dist"] = 0

        default_rows: Dict = fare_table["fare"].to_dict()

        distance_rows = fare_table[(fare_table["dist"] != 0)].index
        zone_rows = fare_table[(fare_table["dist"] == 0)].index

        self.zone_fares: Dict = fare_table["fare"].drop(distance_rows).to_dict()
        try:
            self.exclusive: Dict = fare_table["exclusive"].dropna().to_dict()
        except KeyError:
            self.exclusive = {}
        self.distance_fares: Dict = fare_table[["fare","dist"]].drop(zone_rows).to_dict('index')

        self.default_dist_fare: float = default_rows.pop("dist")
        self.default_start_fare: float = default_rows.pop("start")
