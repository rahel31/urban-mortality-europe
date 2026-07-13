"""
Eurostat Loader — Healthy Cities Project
=========================================
Handles two types of Eurostat files:

1. Urban Audit city-level files (urb_*)
   Structure: 'Urban audit indicator' label, TIME row, CITIES (Labels) rows
   Usage: master = merge_files([...])

2. Country/NUTS2/NUTS3 files with codes (sdg_*, hlth_*, tgs_*, nama_10r_*, demo_r_*)
   Structure: 'TIME\\tTIME\\t<years>' row, 'GEO (Codes)\\tGEO (Labels)' row,
              then CODE | LABEL | values...
   Usage: load_country_file(...) for country-level (2-char codes)
          load_nuts_file(...) for NUTS2 (4-char) or NUTS3 (5-char) codes

Both return LONG format (all years) — merge on code + year and let
snapshot() average across the analysis window automatically.
"""

import os
import re
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════════════
# 1. URBAN AUDIT CITY-LEVEL LOADER
# ═══════════════════════════════════════════════════════════════════════════

MAPPINGS = {
    'total deaths under 65 per year':                                'deaths_under65',
    'number of deaths per year under 65 due to diseases':            'deaths_circulatory_resp',
    'people killed in road accidents per 10000':                     'road_deaths_per10k',
    'number of registered cars per 1000':                            'cars_per1000',
    'population on the 1st of january, total':                       'pop_total',
    'population on the 1st of january, 0-4 years, total':           'pop_0_4',
    'population on the 1st of january, 5-9 years, total':           'pop_5_9',
    'population on the 1st of january, 10-14 years, total':         'pop_10_14',
    'population on the 1st of january, 15-19 years, total':         'pop_15_19',
    'population on the 1st of january, 20-24 years, total':         'pop_20_24',
    'population on the 1st of january, 25-34 years, total':         'pop_25_34',
    'population on the 1st of january, 35-44 years, total':         'pop_35_44',
    'population on the 1st of january, 45-54 years, total':         'pop_45_54',
    'population on the 1st of january, 55-64 years, total':         'pop_55_64',
    'population on the 1st of january, 65-74 years, total':         'pop_65_74',
    'population on the 1st of january, 75 years and over, total':   'pop_75_over',
    'median population age':                                         'median_age',
    'proportion of population aged 65-74':                           'pop_pct_65_74',
    'proportion of population aged 75':                              'pop_pct_75_over',
    'old age dependency ratio':                                      'old_age_dependency',
    'age dependency ratio':                                          'age_dependency',
    'number of murders and violent deaths':                          'murders_violent',
    'median disposable annual household income':                     'median_income',
    'proportion of households that are 1-person':                    'one_person_hh_pct',
    'proportion of households that are lone-pensioner':              'lone_pensioner_hh_pct',
    'share of persons at risk of poverty or social exclusion':       'poverty_exclusion_pct',
    'share of severely materially deprived':                         'material_deprivation_pct',
    'economically active population, 20-64':                         'economically_active',
    'health care services, doctors and hospitals: very satisfied':   'healthcare_very_sat',
    'health care services, doctors and hospitals: rather satisfied': 'healthcare_rather_sat',
    'health care services, doctors and hospitals: rather unsatisfied': 'healthcare_rather_unsat',
    'health care services, doctors and hospitals: very unsatisfied': 'healthcare_very_unsat',
    'how is your health: very good':                                 'health_very_good',
    'how is your health: good':                                      'health_good',
    'how is your health: bad':                                       'health_bad',
    'how is your health: very bad':                                  'health_very_bad',
    'feeling lonely? all of the time':                               'lonely_all_time',
    'feeling lonely? most of the time':                              'lonely_most_time',
    'compared to five years ago quality of life in your city or area has: decreased': 'qol_decreased',
    'compared to five years ago quality of life in your city or area has: increased': 'qol_increased',
    'Persons aged 25-64 with ISCED level 5, 6, 7 or 8 as the highest level of education, from 2014 onwards': 'higher_educ_count',
    
}

COUNTRIES = {
    'Belgium','Bulgaria','Czechia','Czech Republic','Denmark','Germany',
    'Estonia','Ireland','Greece','Spain','France','Croatia','Italy',
    'Cyprus','Latvia','Lithuania','Luxembourg','Hungary','Malta',
    'Netherlands','Austria','Poland','Portugal','Romania','Slovenia',
    'Slovakia','Finland','Sweden','Norway','Switzerland','Iceland',
    'Turkey','United Kingdom','North Macedonia','Serbia','Albania',
    'Montenegro','Bosnia and Herzegovina','Kosovo','EU27','EEA'
}


def _var_name(label: str):
    label_lower = str(label).lower().strip()
    for key, val in MAPPINGS.items():
        if key in label_lower:
            return val
    name = re.sub(r'[^\w\s]', '', label_lower)
    name = re.sub(r'\s+', '_', name.strip())[:40]
    return name


def load_file(filepath: str, verbose: bool = True) -> pd.DataFrame:
    """Load all data sheets from one Eurostat Urban Audit Excel file."""
    xl = pd.ExcelFile(filepath)
    data_sheets = [s for s in xl.sheet_names if 'flag' not in s.lower()]
    all_dfs = []

    for sheet in data_sheets:
        raw = pd.read_excel(filepath, sheet_name=sheet, header=None)

        var_label = time_row = cities_row = None
        for i in range(min(15, len(raw))):
            cell = str(raw.iloc[i, 0])
            if 'Urban audit indicator' in cell:
                var_label = str(raw.iloc[i, 2]).strip()
            if cell.strip() == 'TIME':
                time_row = i
            if 'CITIES' in cell:
                cities_row = i
                break

        if not all([var_label, time_row is not None, cities_row is not None]):
            continue

        var_name = _var_name(var_label)

        years, year_cols = [], []
        for col_idx, val in enumerate(raw.iloc[time_row, 1:], start=1):
            try:
                yr = int(float(val))
                if 2000 <= yr <= 2030:
                    years.append(yr)
                    year_cols.append(col_idx)
            except (ValueError, TypeError):
                pass

        if not years:
            continue

        records = []
        for row_i in range(cities_row + 1, len(raw)):
            city = raw.iloc[row_i, 0]
            if pd.isna(city):
                continue
            city = str(city).strip()
            for yr, col_idx in zip(years, year_cols):
                try:
                    val = pd.to_numeric(raw.iloc[row_i, col_idx], errors='coerce')
                    records.append({'city': city, 'year': yr, var_name: val})
                except IndexError:
                    pass

        df = pd.DataFrame(records).dropna(subset=[var_name])
        all_dfs.append(df)

        if verbose:
            print(f'  {sheet}: [{var_name}] — {df["city"].nunique()} cities, '
                  f'{min(years)}-{max(years)}, {len(df)} values')

    if not all_dfs:
        return pd.DataFrame()

    master = all_dfs[0]
    for df in all_dfs[1:]:
        master = master.merge(df, on=['city', 'year'], how='outer')

    return master.sort_values(['city', 'year']).reset_index(drop=True)


def merge_files(filepaths: list, verbose: bool = True) -> pd.DataFrame:
    """Load and merge multiple Urban Audit files into one master dataframe."""
    master = None
    for fp in filepaths:
        if verbose:
            print(f'\nLoading: {os.path.basename(fp)}')
        df = load_file(fp, verbose=verbose)
        if df.empty:
            continue
        if master is None:
            master = df
        else:
            new_cols = [c for c in df.columns if c not in ['city', 'year']]
            master = master.merge(df[['city', 'year'] + new_cols],
                                  on=['city', 'year'], how='outer')

    if master is not None:
        master = master.sort_values(['city', 'year']).reset_index(drop=True)
    return master


def filter_cities(df: pd.DataFrame) -> pd.DataFrame:
    """Remove country-level aggregate rows."""
    return df[~df['city'].isin(COUNTRIES)].reset_index(drop=True)


def snapshot(master: pd.DataFrame, center: int, window: int = 1) -> pd.DataFrame:
    """Average all variables per city across [center-window, center+window]."""
    subset = master[master['year'].between(center - window, center + window)]
    numeric_cols = [c for c in subset.select_dtypes(include=[np.number]).columns
                    if c != 'year']
    snap = subset.groupby('city')[numeric_cols].mean().reset_index()
    snap.insert(1, 'period', f'{center - window}-{center + window}')
    return snap


# ═══════════════════════════════════════════════════════════════════════════
# 2. CODE-BASED LOADER (country / NUTS2 / NUTS3)
#    Files with 'GEO (Codes)' / 'GEO (Labels)' structure
# ═══════════════════════════════════════════════════════════════════════════

def _load_geo_coded_file(filepath: str, var_name: str, sheet=0,
                         verbose: bool = True) -> pd.DataFrame:
    """
    Shared loader for files with structure:
        TIME | TIME | <year1> | <year2> | ...
        GEO (Codes) | GEO (Labels) |
        <CODE> | <Label> | <val1> | <val2> | ...

    Returns long format: code | year | var_name  (all GEO codes, any length)
    """
    raw = pd.read_excel(filepath, sheet_name=sheet, header=None)

    # Find the row with years: starts with 'TIME' in col 0
    time_row = None
    for i in range(20):
        if str(raw.iloc[i, 0]).strip() == 'TIME':
            time_row = i
            break
    if time_row is None:
        raise ValueError(f'Could not find TIME row in {filepath}')

    # Years start at column index 2 (col 0='TIME', col 1='TIME')
    years, year_cols = [], []
    for col_idx in range(2, raw.shape[1]):
        val = raw.iloc[time_row, col_idx]
        try:
            yr = int(float(val))
            if 2000 <= yr <= 2030:
                years.append(yr)
                year_cols.append(col_idx)
        except (ValueError, TypeError):
            pass

    if not years:
        raise ValueError(f'No years found in {filepath}')

    # Data starts the row after 'GEO (Codes)' row
    geo_row = time_row + 1  # 'GEO (Codes) | GEO (Labels)' row
    data_start = geo_row + 1

    records = []
    for row_i in range(data_start, len(raw)):
        code = raw.iloc[row_i, 0]
        if pd.isna(code):
            continue
        code = str(code).strip()
        for yr, col_idx in zip(years, year_cols):
            val = pd.to_numeric(raw.iloc[row_i, col_idx], errors='coerce')
            records.append({'geo': code, 'year': yr, var_name: val})

    long = pd.DataFrame(records).dropna(subset=[var_name])
    long = long.sort_values(['geo', 'year']).reset_index(drop=True)

    if verbose:
        print(f'  [{var_name}] — {long["geo"].nunique()} regions, '
              f'years {min(years)}-{max(years)}, {len(long)} values')

    return long


def load_country_file(filepath: str, var_name: str, sheet=0,
                      verbose: bool = True) -> pd.DataFrame:
    """
    Load a country-level Eurostat file (codes already 2-letter ISO).
    Filters to 2-character GEO codes only (BE, DE, FR... not EU27_2020 etc).

    Returns long format: Country | year | var_name

    Usage:
        unmet = load_country_file('sdg_03_60.xlsx', 'unmet_medical_pct')
        master = master.merge(unmet, on=['Country', 'year'], how='left')
    """
    long = _load_geo_coded_file(filepath, var_name, sheet, verbose=False)

    # Keep only 2-char ISO country codes
    long = long[long['geo'].str.len() == 2].copy()
    long = long.rename(columns={'geo': 'Country'})
    long = long.sort_values(['Country', 'year']).reset_index(drop=True)

    if verbose:
        print(f'{var_name}: {long["Country"].nunique()} countries, '
              f'years {sorted(long["year"].unique())}, {len(long)} values')

    return long


def load_nuts_file(filepath: str, var_name: str, nuts_level: int = 2,
                   sheet=0, verbose: bool = True) -> pd.DataFrame:
    """
    Load a NUTS2 or NUTS3 regional Eurostat file (codes already included).
    Filters rows by GEO code length: NUTS2=4 chars (BE21), NUTS3=5 chars (BE211).

    Returns long format: NUTS2/NUTS3 | year | var_name

    Usage:
        beds = load_nuts_file('hlth_rs_prsrg.xlsx', 'doctors_count', nuts_level=2)
        gdp  = load_nuts_file('nama_10r_3gdp.xlsx', 'gdp_pps', nuts_level=3)
        dens = load_nuts_file('demo_r_d3dens.xlsx', 'pop_density', nuts_level=3)

        master = master.merge(gdp, on=['NUTS3', 'year'], how='left')
    """
    long = _load_geo_coded_file(filepath, var_name, sheet, verbose=False)

    code_len = nuts_level + 2  # NUTS2=4, NUTS3=5
    long = long[long['geo'].str.len() == code_len].copy()

    nuts_col = f'NUTS{nuts_level}'
    long = long.rename(columns={'geo': nuts_col})
    long = long.sort_values([nuts_col, 'year']).reset_index(drop=True)

    if verbose:
        print(f'{var_name}: {long[nuts_col].nunique()} NUTS{nuts_level} regions, '
              f'years {sorted(long["year"].unique())}, {len(long)} values')

    return long
