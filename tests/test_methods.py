#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitGub: https://github.com/btschwertfeger
#

"""Module to to test the bias adjustment methods"""

import unittest
from typing import List, Tuple

import numpy as np
import pytest
import xarray as xr
from sklearn.metrics import mean_squared_error

from cmethods import CMethods
from cmethods.static import DISTRIBUTION_METHODS, SCALING_METHODS
from cmethods.types import XRData_t
from cmethods.utils import UnknownMethodError


class TestMethods(unittest.TestCase):
    def setUp(self) -> None:
        obsh_add, obsp_add, simh_add, simp_add = self.get_datasets(kind="+")
        obsh_mult, obsp_mult, simh_mult, simp_mult = self.get_datasets(kind="*")

        self.data = {
            "+": {
                "obsh": obsh_add["+"],
                "obsp": obsp_add["+"],
                "simh": simh_add["+"],
                "simp": simp_add["+"],
            },
            "*": {
                "obsh": obsh_mult["*"],
                "obsp": obsp_mult["*"],
                "simh": simh_mult["*"],
                "simp": simp_mult["*"],
            },
        }
        self.cm = CMethods()

    def get_datasets(
        self,
        kind: str,
    ) -> Tuple[xr.Dataset, xr.Dataset, xr.Dataset, xr.Dataset]:
        historical_time = xr.cftime_range(
            "1971-01-01", "2000-12-31", freq="D", calendar="noleap"
        )
        future_time = xr.cftime_range(
            "2001-01-01", "2030-12-31", freq="D", calendar="noleap"
        )
        latitudes = np.arange(23, 27, 1)

        def get_hist_temp_for_lat(lat: int) -> List[float]:
            """Returns a fake interval time series by latitude value"""
            return 273.15 - (
                lat * np.cos(2 * np.pi * historical_time.dayofyear / 365)
                + 2 * np.random.random_sample((historical_time.size,))
                + 273.15
                + 0.1 * (historical_time - historical_time[0]).days / 365
            )

        def get_fake_hist_precipitation_data() -> List[float]:
            """Returns ratio based fake time series"""
            pr = (
                np.cos(2 * np.pi * historical_time.dayofyear / 365)
                * np.cos(2 * np.pi * historical_time.dayofyear / 365)
                * np.random.random_sample((historical_time.size,))
            )

            pr *= 0.0004 / pr.max()  # scaling
            years = 30
            days_without_rain_per_year = 239

            c = days_without_rain_per_year * years  # avoid rain every day
            pr.ravel()[np.random.choice(pr.size, c, replace=False)] = 0
            return pr

        def get_dataset(data, time, kind: str) -> xr.Dataset:
            """Returns a data set by data and time"""
            return (
                xr.DataArray(
                    data,
                    dims=("lon", "lat", "time"),
                    coords={"time": time, "lat": latitudes, "lon": [0, 1, 3]},
                )
                .transpose("time", "lat", "lon")
                .to_dataset(name=kind)
            )

        if kind == "+":
            some_data = [get_hist_temp_for_lat(val) for val in latitudes]
            data = np.array(
                [
                    np.array(some_data),
                    np.array(some_data) + 0.5,
                    np.array(some_data) + 1,
                ]
            )
            obsh = get_dataset(data, historical_time, kind=kind)
            obsp = get_dataset(data + 1, historical_time, kind=kind)
            simh = get_dataset(data - 2, historical_time, kind=kind)
            simp = get_dataset(data - 1, future_time, kind=kind)

        else:  # precipitation
            some_data = [get_fake_hist_precipitation_data() for _ in latitudes]
            data = np.array(
                [some_data, np.array(some_data) + np.random.rand(), np.array(some_data)]
            )
            obsh = get_dataset(data, historical_time, kind=kind)
            obsp = get_dataset(data * 1.02, historical_time, kind=kind)
            simh = get_dataset(data * 0.98, historical_time, kind=kind)
            simp = get_dataset(data * 0.09, future_time, kind=kind)

        return obsh, obsp, simh, simp

    # --------------------------------------------------------------------------
    # 1-dimensional

    def test_linear_scaling(self) -> None:
        """Tests the linear scaling method"""

        for kind in ("+", "*"):
            ls_result = self.cm.adjust(
                method="linear_scaling",
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                kind=kind,
            )
            assert isinstance(ls_result, XRData_t)
            assert mean_squared_error(
                ls_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_variance_scaling(self) -> None:
        """Tests the variance scaling method"""
        kind = "+"
        vs_result = self.cm.adjust(
            method="variance_scaling",
            obs=self.data[kind]["obsh"][:, 0, 0],
            simh=self.data[kind]["simh"][:, 0, 0],
            simp=self.data[kind]["simp"][:, 0, 0],
            kind="+",
        )
        assert isinstance(vs_result, XRData_t)
        assert mean_squared_error(
            vs_result, self.data[kind]["obsp"][:, 0, 0], squared=False
        ) < mean_squared_error(
            self.data[kind]["simp"][:, 0, 0],
            self.data[kind]["obsp"][:, 0, 0],
            squared=False,
        )

    def test_delta_method(self) -> None:
        """Tests the delta method"""

        for kind in ("+", "*"):
            dm_result = self.cm.adjust(
                method="delta_method",
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                kind=kind,
            )
            assert isinstance(dm_result, XRData_t)
            assert mean_squared_error(
                dm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_quantile_mapping(self) -> None:
        """Tests the quantile mapping method"""

        for kind in ("+", "*"):
            qm_result = self.cm.adjust(
                method="quantile_mapping",
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                n_quantiles=100,
                kind=kind,
            )
            assert isinstance(qm_result, XRData_t)
            assert mean_squared_error(
                qm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_detrended_quantile_mapping(self) -> None:
        """Tests the detrended quantile mapping method"""

        for kind in ("+", "*"):
            dqm_result = self.cm.adjust(
                method="detrended_quantile_mapping",
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                n_quantiles=100,
                kind=kind,
                group="time.month",
            )
            assert isinstance(dqm_result, XRData_t)
            assert mean_squared_error(
                dqm_result[kind], self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_quantile_delta_mapping(self) -> None:
        """Tests the quantile delta mapping method"""

        for kind in ("+", "*"):
            qdm_result = self.cm.adjust(
                method="quantile_delta_mapping",
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                n_quantiles=100,
                kind=kind,
            )

            assert isinstance(qdm_result, XRData_t)
            if np.isnan(qdm_result).any():
                raise ValueError(qdm_result)
            assert mean_squared_error(
                qdm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    # --------------------------------------------------------------------------
    # 3-dimensional

    def test_3d_sclaing_methods(self) -> None:
        """Tests the scaling based methods for 3-dimensional data sets"""

        for kind in ("+", "*"):
            for method in SCALING_METHODS:
                if kind == "*" and method == "variance_scaling":
                    continue

                result = self.cm.adjust(
                    method=method,
                    obs=self.data[kind]["obsh"],
                    simh=self.data[kind]["simh"],
                    simp=self.data[kind]["simp"],
                    kind=kind,
                    group="time.month",
                )
                assert isinstance(result, XRData_t)
                for lat in range(len(self.data[kind]["obsh"].lat)):
                    for lon in range(len(self.data[kind]["obsh"].lon)):
                        assert mean_squared_error(
                            result[kind][:, lat, lon],
                            self.data[kind]["obsp"][:, lat, lon],
                            squared=False,
                        ) < mean_squared_error(
                            self.data[kind]["simp"][:, lat, lon],
                            self.data[kind]["obsp"][:, lat, lon],
                            squared=False,
                        )

    def test_3d_distribution_methods(self) -> None:
        """Tests the distribution based methods for 3-dimensional data sets"""

        for kind in ("+", "*"):
            for method in DISTRIBUTION_METHODS:
                kwargs: dict = {}
                if method == "detrended_quantile_mapping":
                    kwargs = {"group": "time.month"}

                result = self.cm.adjust(
                    method=method,
                    obs=self.data[kind]["obsh"],
                    simh=self.data[kind]["simh"],
                    simp=self.data[kind]["simp"],
                    n_quantiles=25,
                    kind=kind,
                    **kwargs,
                )
                assert isinstance(result, XRData_t)
                for lat in range(len(self.data[kind]["obsh"].lat)):
                    for lon in range(len(self.data[kind]["obsh"].lon)):
                        assert mean_squared_error(
                            result[:, lat, lon],
                            self.data[kind]["obsp"][:, lat, lon],
                            squared=False,
                        ) < mean_squared_error(
                            self.data[kind]["simp"][:, lat, lon],
                            self.data[kind]["obsp"][:, lat, lon],
                            squared=False,
                        )

    # --------------------------------------------------------------------------
    # misc
    def test_n_jobs(self) -> None:
        kind = "+"
        result = self.cm.adjust(
            method="quantile_mapping",
            obs=self.data[kind]["obsh"],
            simh=self.data[kind]["simh"],
            simp=self.data[kind]["simp"],
            n_quantiles=25,
        )
        assert isinstance(result, XRData_t)
        for lat in range(len(self.data[kind]["obsh"].lat)):
            for lon in range(len(self.data[kind]["obsh"].lon)):
                assert mean_squared_error(
                    result[:, lat, lon],
                    self.data[kind]["obsp"][:, lat, lon],
                    squared=False,
                ) < mean_squared_error(
                    self.data[kind]["simp"][:, lat, lon],
                    self.data[kind]["obsp"][:, lat, lon],
                    squared=False,
                )

    # --------------------------------------------------------------------------
    # test failures
    def test_unknown_method(self) -> None:
        with pytest.raises(UnknownMethodError):
            self.cm.get_function("LOCI_INTENSITY_SCALING")

        kind = "+"
        with pytest.raises(UnknownMethodError):
            self.cm.adjust(
                method="distribution_mapping",
                obs=self.data[kind]["obsh"],
                simh=self.data[kind]["simh"],
                simp=self.data[kind]["simp"],
                kind=kind,
            )

    def test_not_implemented_methods(self) -> None:
        kind = "+"
        with pytest.raises(NotImplementedError):
            self.cm.get_function(method="empirical_quantile_mapping")(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                n_quantiles=10,
            )

    def test_invalid_adjustment_type(self) -> None:
        kind = "+"
        obs = list(self.data[kind]["obsh"])
        simh = list(self.data[kind]["simh"])
        simp = list(self.data[kind]["simp"])
        with pytest.raises(NotImplementedError):
            self.cm._CMethods__linear_scaling(  # type: ignore[attr-defined]
                obs,
                simh,
                simp,
                kind="/",
            )

        with pytest.raises(NotImplementedError):
            self.cm._CMethods__variance_scaling(  # type: ignore[attr-defined]
                obs,
                simh,
                simp,
                kind="*",
            )

        with pytest.raises(NotImplementedError):
            self.cm._CMethods__delta_method(  # type: ignore[attr-defined]
                obs,
                simh,
                simp,
                kind="/",
            )

        with pytest.raises(NotImplementedError):
            self.cm._CMethods__quantile_mapping(  # type: ignore[attr-defined]
                obs,
                simh,
                simp,
                kind="/",
                n_quantiles=10,
            )

        with pytest.raises(NotImplementedError):
            self.cm._CMethods__detrended_quantile_mapping(  # type: ignore[attr-defined]
                obs,
                simh,
                simp,
                kind="/",
                n_quantiles=10,
                xbins=[1, 2, 3, 4],
                cdf_simh=[1, 2, 3],
                cdf_obs=[1, 2, 3],
            )

        with pytest.raises(NotImplementedError):
            self.cm._CMethods__quantile_delta_mapping(  # type: ignore[attr-defined]
                obs,
                simh,
                simp,
                kind="/",
                n_quantiles=10,
            )


if __name__ == "__main__":
    unittest.main()
