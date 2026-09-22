"""One-off addition of generator boundary conditions, never overwrite manual edits."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    path=ROOT/'data'/'live'/'telemetry.csv'
    frame=pd.read_csv(path)
    # These values are known only for the initial W27 fixture calculated at fixed conditions.
    audit=json.loads((ROOT/'data'/'prosper_diagnostic_audit_W27.json').read_text(encoding='utf-8'))
    conditions=audit['physical_scenarios']['fixed_conditions']
    values={'whp_bara':conditions['whp_psig']*.0689475729+1.01325,
            'water_cut_pct':conditions['wc_pct'],'gor_m3m3':conditions['gor_scf_stb']*.178107606679035}
    for key,value in values.items():
        if key not in frame: frame[key]=float('nan')
        mask=(frame.well_id=='W_BEL_27_TLBB') & frame[key].isna()
        frame.loc[mask,key]=value
    frame.to_csv(path,index=False)
    print('Initial W27 boundary conditions added; existing measurements preserved')


if __name__=='__main__': main()
