"""
EEA END Noise Loader — Healthy Cities Project
==============================================
Loads road and rail noise data from two END Excel files (2017 and 2022).
Returns one clean dataframe with % population exposed to noise >=55dB.

USAGE IN JUPYTER
----------------
from load_noise import load_noise

noise = load_noise(
    file_2017='Noise_data/END_2017.xlsx',
    file_2022='Noise_data/END_2022.xlsx'
)

# Result columns:
# city | year | road_lden_pct_55 | road_lnight_pct_55 | rail_lden_pct_55 | rail_lnight_pct_55

# Merge with snapshots in Jupyter:
# df_early = df_early.merge(noise[noise['year']==2017].drop(columns='year'), on='city', how='left')
# df_late  = df_late.merge(noise[noise['year']==2022].drop(columns='year'), on='city', how='left')

MISSING VALUE HANDLING
-----------------------
'No data'        -> NaN (genuinely missing, city did not report)
'Not applicable' -> 0   (e.g. no major rail line, legitimately zero exposure)

If ANY band for a city is 'No data', the whole Lden/Lnight sum for that
city becomes NaN — a city showing 0% noise exposure means "measured zero",
NOT "no data available". This distinction matters: silently treating
missing data as 0 would make unreported cities look artificially quiet.
"""

import pandas as pd
import numpy as np


def _sum_or_nan(row, cols):
    """
    Sum the given columns for one row.
    If ANY value is NaN (i.e. was 'No data'), return NaN for the whole sum
    rather than silently treating it as 0.
    'Not applicable' values are pre-converted to 0 before this function runs,
    so they sum normally (legitimately zero exposure).
    """
    values = [pd.to_numeric(row[c], errors='coerce') for c in cols]
    if any(pd.isna(v) for v in values):
        return np.nan
    return sum(values)


def _load_sheet(filepath: str, sheet: str, year: int, source: str) -> pd.DataFrame:
    """
    Load one noise sheet and return city-level exposure percentages.
    source: 'road' or 'rail'
    """
    df = pd.read_excel(filepath, sheet_name=sheet)

    # 'No data' -> NaN (missing), 'Not applicable' -> 0 (legitimately zero)
    df = df.replace({
        'No data': np.nan, 'No data ': np.nan,
        'Not applicable': 0, 'Not applicable ': 0,
    })

    # Find city column
    city_col = next((c for c in df.columns
                     if 'agglomeration' in str(c).lower()), None)
    inhab_col = next((c for c in df.columns
                      if 'inhabitants' in str(c).lower()), None)

    if not city_col or not inhab_col:
        print(f'  ERROR: city or inhabitants column not found in {sheet}')
        return pd.DataFrame()

    # Lden >=55 columns: contain Lden (or lden) but NOT Lnight/lnight
    lden_cols = [c for c in df.columns
                 if 'lden' in str(c).lower()
                 and 'night' not in str(c).lower()
                 and any(b in str(c) for b in
                         ['55-59', '60-64', '65-69', '70-74', '>75'])]

    # Lnight >=55 columns: contain Lnight (or lnight)
    lnight_cols = [c for c in df.columns
                   if 'lnight' in str(c).lower()
                   and any(b in str(c) for b in
                           ['55-59', '60-64', '65-69', '>70', '>75'])]

    if not lden_cols:
        print(f'  WARNING: no Lden >=55 columns found in {sheet}')
        print(f'  Available columns: {df.columns.tolist()}')
        return pd.DataFrame()

    records = []
    for _, row in df.iterrows():
        city = str(row[city_col]).strip()
        if not city or city in ('nan', 'CITIES (Labels)'):
            continue

        inhab = pd.to_numeric(row[inhab_col], errors='coerce')
        if pd.isna(inhab) or inhab <= 0:
            continue

        lden_55   = _sum_or_nan(row, lden_cols)
        lnight_55 = _sum_or_nan(row, lnight_cols)

        records.append({
            'city':                       city,
            'nr_inhabitants':             inhab,
            f'{source}_lden_pct_55':   (round(lden_55   / inhab * 100, 2)
                                         if not pd.isna(lden_55) else np.nan),
            f'{source}_lnight_pct_55': (round(lnight_55 / inhab * 100, 2)
                                         if not pd.isna(lnight_55) else np.nan),
        })

    result = pd.DataFrame(records)
    n_missing_lden = result[f'{source}_lden_pct_55'].isna().sum()
    print(f'  {sheet} ({year}): {len(result)} agglomerations '
          f'({n_missing_lden} with no Lden data), '
          f'Lden cols: {lden_cols}, Lnight cols: {lnight_cols}')
    return result


def _load_year(filepath: str, year: int) -> pd.DataFrame:
    """Load road + rail from one END file and merge on city."""
    road = _load_sheet(filepath, 'Aggl_Road_Data', year, 'road')
    rail = _load_sheet(filepath, 'Aggl_Rail_Data', year, 'rail')

    if road.empty and rail.empty:
        return pd.DataFrame()

    if road.empty:
        merged = rail.drop(columns=['nr_inhabitants'], errors='ignore')
    elif rail.empty:
        merged = road.drop(columns=['nr_inhabitants'], errors='ignore')
    else:
        merged = road[['city', 'road_lden_pct_55', 'road_lnight_pct_55']].merge(
            rail[['city', 'rail_lden_pct_55', 'rail_lnight_pct_55']],
            on='city', how='outer'
        )

    merged['year'] = year
    return merged[['city', 'year',
                   'road_lden_pct_55', 'road_lnight_pct_55',
                   'rail_lden_pct_55', 'rail_lnight_pct_55']]


def load_noise(file_2017: str, file_2022: str) -> pd.DataFrame:
    """
    Load both END files and return one combined long-format dataframe.

    Returns:
        city | year | road_lden_pct_55 | road_lnight_pct_55 |
        rail_lden_pct_55 | rail_lnight_pct_55

    NaN means "no data reported" (not zero exposure).
    """
    print('Loading 2017 noise data...')
    df_2017 = _load_year(file_2017, 2017)

    print('\nLoading 2022 noise data...')
    df_2022 = _load_year(file_2022, 2022)

    noise = pd.concat([df_2017, df_2022], ignore_index=True)
    noise = noise.sort_values(['city', 'year']).reset_index(drop=True)

    print(f'\nNoise dataset: {len(noise)} rows, '
          f'{noise["city"].nunique()} unique cities, '
          f'years: {sorted(noise["year"].unique())}')
    return noise
