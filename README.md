# scs_insurance_claims

Deep exploratory analysis of Millennium Mutual's policy and claim exports. The notebook's sole purpose is EDA: no predictive model, app, or automation.

Start with the [executed notebook](output/jupyter-notebook/insurance_claims_eda.ipynb), or download and open the [HTML companion](output/jupyter-notebook/insurance_claims_eda.html) to read all outputs without Python.

The analysis includes **144 cells, 185 figures, and 185 exported CSV tables** across 21 sections:

- Raw schema, inferred column dictionary, missingness, duplicates, date parsing, and key integrity.
- Numeric distributions, tails, categorical counts, and category-versus-number galleries with mean/median bars and boxplots.
- Pearson/Spearman correlations, pairwise sample sizes, scatterplots, categorical associations, and cross-tabs.
- Two-dimensional pivot tables (*tableaux croisés dynamiques*) with counts and sparse-cell masking.
- Policy cohorts, calendar patterns, portfolio mix, and focused broker B07 comparisons.
- Team processing times, backlog ages, case mix, and completion rates with equal follow-up.
- The $10,000 review threshold, payout/deductible reconciliation, renewal experience, and transparent anomaly screens.
- Sensitivity checks and an evidence summary with interpretation limits.

## Run

Use Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --locked
uv run jupyter lab
```

Open `output/jupyter-notebook/insurance_claims_eda.ipynb` and run all cells. The notebook locates the repository from either its own directory or the repository root. It needs no credentials or network access to analyze the included CSVs.

To execute and regenerate the HTML from the command line:

```bash
uv run jupyter nbconvert --to notebook --execute --inplace output/jupyter-notebook/insurance_claims_eda.ipynb --ExecutePreprocessor.timeout=300
uv run jupyter nbconvert --to html output/jupyter-notebook/insurance_claims_eda.ipynb
```

## Data and interpretation

- `data/raw/policies.csv`: 4,684 original policy rows.
- `data/raw/claims.csv`: 862 original export rows; 847 unique claims after removing 15 exact duplicate rows.
- `references/business_track_participants.pdf`: supplied scenario, used as context. Its prototype and automation requirements are outside this EDA request.
- `output/eda/tables/`: reproducible summaries, pivots, cross-tabs, row-level review evidence, and a figure inventory.
- `pyproject.toml` and `uv.lock`: dependency definitions and locked environment.

The snapshot is **October 31, 2026**. Raw CSVs are preserved; the notebook records their SHA-256 hashes and every cleaning decision. Currency is assumed CAD from the scenario. Dates with slashes are interpreted as day/month/year.

Recorded payouts divided by annual premium are a cohort comparison proxy, not profit or an actuarial loss ratio. Recent cohorts have less follow-up. Renewal comparisons use matured policies and pre-anniversary claim experience. Statistical flags are inspection leads, not fraud labels or causal conclusions.

All 96 code cells were executed top to bottom, all 185 figures are embedded in the notebook and HTML, and representative charts were visually reviewed. No tests or Python docstrings were added.
