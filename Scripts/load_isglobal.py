"""
ISGlobal Environmental Data Loader — Healthy Cities Project
============================================================
Loads air pollution (PM2.5, NO2) and green space (NDVI, GA%) data
from ISGlobal/Lancet Planetary Health supplementary files.
All data is for reference year 2015.

FILE STRUCTURE EXPECTED
-----------------------
air_file:  City_code | Median PM2.5 (ug/m3) | Median NO2 (ug/m3)
ndvi_file: City_code | NDVI level (mean)
ga_file:   City_code | City | Percentage of GA (mean) | Year

USAGE IN JUPYTER
----------------
from load_isglobal import load_isglobal

env = load_isglobal(
    air_file  = 'DATA/Other_sources/City_air_pol.xlsx',
    ndvi_file = 'DATA/Other_sources/City_green_NDVI.xlsx',
    ga_file   = 'DATA/Other_sources/City_green_GA_perc.xlsx',
)

# Merge with master snapshot on city_code or city name
"""

import pandas as pd


def load_isglobal(air_file: str, ndvi_file: str, ga_file: str,
                  verbose: bool = True) -> pd.DataFrame:

    def read_file(path):
        if path.endswith('.csv'):
            return pd.read_csv(path, sep=None, engine='python')
        return pd.read_excel(path)

    # ── Air pollution — city_code only ─────────────────────────────────────
    air = read_file(air_file)
    air.columns = [c.strip() for c in air.columns]
    air = air.rename(columns={
        'City_code':            'city_code',
        'Median PM2.5 (ug/m3)': 'pm25_median',
        'Median NO2 (ug/m3)':   'no2_median',
    })
    air = air[['city_code', 'pm25_median', 'no2_median']].copy()
    if verbose:
        print(f'Air pollution: {len(air)} cities')

    # ── NDVI — city_code only ──────────────────────────────────────────────
    ndvi = read_file(ndvi_file)
    ndvi.columns = [c.strip() for c in ndvi.columns]
    ndvi = ndvi.rename(columns={
        'City_code':         'city_code',
        'NDVI level (mean)': 'ndvi_mean',
    })
    ndvi = ndvi[['city_code', 'ndvi_mean']].copy()
    if verbose:
        print(f'NDVI:          {len(ndvi)} cities')

    # ── Green area % — has city name and year ──────────────────────────────
    ga = read_file(ga_file)
    ga.columns = [c.strip() for c in ga.columns]
    ga = ga.rename(columns={
        'City_code':               'city_code',
        'City':                    'city',
        'Percentage of GA (mean)': 'ga_pct_mean',
        'Year':                    'year',
    })
    ga = ga[['city_code', 'city', 'year', 'ga_pct_mean']].copy()
    if verbose:
        print(f'Green area %:  {len(ga)} cities')

    # ── Merge all on city_code — start with GA (has city + year) ──────────
    merged = ga.merge(air,  on='city_code', how='outer')
    merged = merged.merge(ndvi, on='city_code', how='outer')

    merged = merged[['city_code', 'city', 'year',
                      'pm25_median', 'no2_median',
                      'ndvi_mean', 'ga_pct_mean']]
    merged = merged.sort_values('city_code').reset_index(drop=True)

    if verbose:
        print(f'\nMerged ISGlobal dataset: {len(merged)} cities')
        print(f'PM2.5 coverage:  {merged["pm25_median"].notna().sum()}')
        print(f'NO2 coverage:    {merged["no2_median"].notna().sum()}')
        print(f'NDVI coverage:   {merged["ndvi_mean"].notna().sum()}')
        print(f'Green area %:    {merged["ga_pct_mean"].notna().sum()}')

    return merged
