# %%
from dataclasses import dataclass, field
from itertools import product, chain, combinations
from linearmodels import IV2SLS
from linearmodels.iv.results import IVResults
from src import Paths
from statsmodels.api import add_constant
from toolz import pipe
from typing import Union, List, Tuple
import numpy as np
import os
import pandas as pd
import pickle as pkl


# %%
@dataclass(frozen=True)
class Data:
    dependent: Union[pd.Series, pd.DataFrame, np.ndarray]
    exog: Union[pd.Series, pd.DataFrame, np.ndarray]
    endog: Union[pd.Series, pd.DataFrame, np.ndarray]
    instrument: Union[pd.Series, pd.DataFrame, np.ndarray]
    weights: Union[pd.Series, pd.DataFrame, np.ndarray]
    cluster: Union[pd.Series, pd.DataFrame, np.ndarray]


@dataclass(frozen=True)
class Grid:
    dependent: List[str]
    exog: List[List[str]]


@dataclass
class Results:
    dependent: List[str] = field(default_factory=list)
    exog: List[Tuple[str]] = field(default_factory=list)
    iv: List[IVResults] = field(default_factory=list)

    def add_iv(self, dependent: str, exog: List[str], iv: IVResults):
        self.dependent.append(dependent)
        self.exog.append(exog)
        self.iv.append(iv)

    def mutate(self, name, values):
        setattr(self, name, values)


# %%
paths = Paths(
    project=os.path.join(
        os.path.expanduser("~"), "Documents", "GitHub", "inequality-by-education"
    ),
    data=os.path.join(
        os.path.expanduser("~"),
        "Documents",
        "GitHub",
        "inequality-by-education",
        "data",
    ),
)


# %%
def load_data() -> Data:

    data = pkl.load(open(paths.join(paths.data, "data.pkl"), "rb")).reset_index(
        level="statefip"
    )

    data_struct = Data(
        dependent=pipe(
            data,
            lambda x: x[["Dnilf_rate_c", "Dunemp_rate_c", "Dln_wage_c"]],
            lambda x: x.xs(("", ""), level=("year", "is_low"), axis=1),
        ),
        exog=pipe(
            data,
            lambda x: x.xs((1990, 0), level=("year", "is_low"), axis=1),
            lambda x: x.drop(columns="index"),
            lambda x: add_constant(x),
        ),
        endog=pipe(
            data,
            lambda x: x["x"],
            lambda x: pd.DataFrame(x),
        ),
        instrument=pipe(
            data,
            lambda x: x["z"],
            lambda x: pd.DataFrame(x),
        ),
        weights=pipe(
            data,
            lambda x: x["weight"],
            lambda x: pd.DataFrame(x),
        ),
        cluster=pipe(
            data,
            lambda x: x["statefip"],
            lambda x: pd.DataFrame(x),
        ),
    )
    return data_struct


data = load_data()
# %%

grid = Grid(
    dependent=["Dnilf_rate_c", "Dunemp_rate_c", "Dln_wage_c"],
    exog=pipe(
        data.exog,
        lambda x: x.drop(columns="const"),
        lambda x: x.columns.tolist(),
        lambda x: [list(combinations(x, i)) for i in range(1, len(x) + 1)],
        lambda x: chain(*x),
        lambda x: list(x),
        lambda x: [["const"] + list(i) for i in x],
        lambda x: [["const"]] + x,
    ),
)
# %%
results = Results()

for y, w in product(grid.dependent, grid.exog):
    try:
        results.add_iv(
            dependent=y,
            exog=tuple(w),
            iv=IV2SLS(
                dependent=data.dependent[y],
                exog=data.exog[w],
                endog=data.endog,
                instruments=data.instrument,
                weights=data.weights / data.weights.sum(),
            ).fit(cov_type="clustered", clusters=data.cluster),
        )
    except ValueError as e:
        continue

results.mutate(name="first_stage", values=[i.first_stage for i in results.iv])

results.mutate(
    name="f_stat",
    values=[float(i.diagnostics["f.stat"].x) for i in results.first_stage],
)

results.mutate(
    name="f_pval",
    values=[float(i.diagnostics["f.pval"].x) for i in results.first_stage],
)

with open(paths.join(paths.data, "results.pkl"), "wb") as f:
    pipe(
        results,
        lambda x: x.__dict__,
        lambda x: pd.DataFrame(x),
        lambda x: pkl.dump(x, f),
    )
# %%
data.endog


# %%
def weighted_percentile(data, weights, percentile):
    """
    Calculates the weighted percentile of a dataset.

    :param data: List or array of numerical data.
    :param weights: List or array of weights corresponding to the data.
    :param percentile: Desired percentile (between 0 and 100).
    :return: The value of the weighted percentile.
    """
    if len(data) != len(weights):
        raise ValueError("Data and weights must have the same length.")
    if not (0 <= percentile <= 100):
        raise ValueError("Percentile must be between 0 and 100.")

    # Normalize weights
    weights = np.array(weights) / np.sum(weights)

    # Sort data and weights
    sorted_indices = np.argsort(data)
    sorted_data = np.array(data)[sorted_indices]
    sorted_weights = weights[sorted_indices]

    # Compute cumulative weighted distribution
    cumulative_weights = np.cumsum(sorted_weights)

    # Find the percentile value
    percentile_fraction = percentile / 100.0
    return sorted_data[np.searchsorted(cumulative_weights, percentile_fraction)]


# %%
wp = lambda x: weighted_percentile(
    data.endog.values.flatten(), data.weights.values.flatten(), x
)
# %%
(wp(75) - wp(25))
