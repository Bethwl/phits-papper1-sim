"""
Sinh tự động file .inp cho PHITS từ bảng bề dày (Energy x s1..s6) trong Excel.
Chạy: python generate_inputs.py thickness_table.xlsx inputs/

Moi job gio co 3 tally:
  1) T-Track total fluence (co buildup)   - axis=reg, 1 bin nang luong duy nhat
  2) T-Track spectrum near peak (uncollided) - axis=eng, nhieu bin, chi quet vung
     sat dinh nang luong nguon (emin_peak..e0) de tach flux one-way.
  3) T-Cross full spectrum (log) - quet toan pho tu 0.001 MeV den 1.1*e0,
     chia log (e-type=3), dung de tinh buildup factor va doi chieu tong
     fluence voi XCOM/FLUKA. Hinh hoc khop voi file .inp chuan da kiem tra
     (ban kinh lo chuan truc 0.25, r0=0.0, mat truoc/sau collimator 1 tai
     z=2.0/12.0, bien ngoai lui them 7.5 sau day do).
"""
import sys
import math
import pandas as pd
from pathlib import Path

# Thanh phan vat lieu (wt fraction, am = weight fraction theo PHITS)
COMPOSITION = {
    "s1": {"5000.00c": -0.1629, "8000.00c": -0.4648, "14000.00c": -0.0302, "20000.00c": -0.0431, "57000.00c": -0.2990},
    "s2": {"5000.00c": -0.1329, "8000.00c": -0.4086, "14000.00c": -0.0266, "20000.00c": -0.0379, "57000.00c": -0.3941},
    "s3": {"5000.00c": -0.1095, "8000.00c": -0.3644, "14000.00c": -0.0237, "20000.00c": -0.0338, "57000.00c": -0.4688},
    "s4": {"5000.00c": -0.0905, "8000.00c": -0.3289, "14000.00c": -0.0214, "20000.00c": -0.0305, "57000.00c": -0.5288},
    "s5": {"5000.00c": -0.0750, "8000.00c": -0.2996, "14000.00c": -0.0195, "20000.00c": -0.0278, "57000.00c": -0.5783},
    "s6": {"5000.00c": -0.0620, "8000.00c": -0.2752, "14000.00c": -0.0179, "20000.00c": -0.0255, "57000.00c": -0.6195},
}
DENSITY = {"s1": 3.0099, "s2": 3.1999, "s3": 3.3899, "s4": 3.5799, "s5": 3.7699, "s6": 3.9599}

# Vi tri hinh hoc co dinh (khop file .inp chuan), chi doi mat 12/13/14 theo be day mau
Z_COLLIM1_FRONT = 2.0
Z_COLLIM1_BACK = 12.0        # mat 11: mat truoc mau (co dinh)
COLLIM2_LEN = 10.0           # chieu dai ong chuan truc 2 (co dinh)
DET_LEN = 5.0                # chieu day dau do NaI (co dinh)
SOURCE_R0 = 0.0              # ban kinh chum nguon (r0 trong [Source]), khop file chuan
Z_OUTER_MARGIN = 7.5         # khoang lui bien ngoai (surface 25) sau day do, khop file chuan

# Tham so tally phong pho gan dinh (de tach flux uncollided / one-way)
PEAK_FRACTION = 0.9   # emin_peak = PEAK_FRACTION * e0  -> quet 10% vung sat dinh
NE_PEAK = 100         # so bin trong vung sat dinh

# Tham so tally T-Cross bo sung: pho log TOAN PHAN (khong chi vung dinh), dung de
# tinh buildup factor va doi chieu tong fluence voi XCOM/FLUKA. Hinh hoc (ban kinh
# lo 0.2, r0=0.1, khong dich truc z) giu nguyen vi da khop XCOM, chi them tally.
HOLE_RADIUS = 0.25                         # khop voi surface 20 = cz 0.25 (theo file .inp chuan)
CROSS_AREA = math.pi * HOLE_RADIUS ** 2    # dien tich mat cat T-Cross (~0.125664 cm^2)
CROSS_EMIN_ABS = 0.001                     # MeV, tran tren cho emin (khong vuot qua 1 keV)
CROSS_EMIN_FRACTION = 0.1                  # emin khong vuot qua 10% cua e0 (tranh emin>=emax
                                            # khi e0 rat thap, vi du 1-50 keV trong seri quet)
CROSS_EMAX_FACTOR = 1.1                    # emax = 1.1 * e0 (du du de bat het dinh nang luong)
CROSS_NE = 100                             # so bin log cho ca phong

TEMPLATE = """Narrow Beam Gamma Shielding - Material {mat_upper} @ {energy_kev} keV

[ Parameters ]
icntl    = 0
nucdata  = 0
maxcas   = 1000000
maxbch   = 1
file(6)  = phits_{mat}_{energy_kev}keV.out

[ Source ]
totfact  = 1.0
s-type   = 1
x0       = 0.0
y0       = 0.0
z0       = 0.0
z1       = 0.0
proj     = photon
e0       = {e0_mev:.6f}
dir      = 1
r0       = {source_r0}

[ Material ]
m1    82000.00c  1.0

m2    {mat_comp}

m3    11000.00c  -0.153
      53000.00c  -0.847

[ Surface ]
10  pz   {z_c1f}
11  pz   {z_c1b}
12  pz   {z_sample_back:.4f}
13  pz   {z_c2b:.4f}
14  pz   {z_det_back:.4f}
15  pz   0.0
24  pz  -5.0
25  pz  {z_outer:.4f}

20  cz   {hole_radius}
21  cz   1.0
22  cz   2.5
23  cz   5.0
99  so 100.0

[ Cell ]
101   1 -11.34   10 -11 -21 20
102   0          10 -11 -20
103   2 -{density}  11 -12 -22
104   1 -11.34   12 -13 -21 20
105   0          12 -13 -20
106   3 -3.67    13 -14 -23
110   0          -99 #101 #102 #103 #104 #105 #106
111  -1          99

[ Volume ]
reg   vol
106   392.7

[ T-Track ]
title = Total fluence of Photons in Detector (with buildup)
mesh  = reg
reg   = 106
part  = photon
e-type = 2
ne    = 1
emin  = 0.0
emax  = {e0_mev:.6f}
unit  = 1
axis  = reg
file  = flux_total_{mat}_{energy_kev}keV.out

[ T-Track ]
title = Fluence spectrum near peak (for uncollided extraction)
mesh  = reg
reg   = 106
part  = photon
e-type = 2
ne    = {ne_peak}
emin  = {emin_peak:.6f}
emax  = {e0_mev:.6f}
unit  = 1
axis  = eng
file  = flux_spectrum_{mat}_{energy_kev}keV.out

[ T-Cross ]
title = Fluence crossing detector entrance face (T-Cross method, kieu FLUKA USRBDX)
mesh  = reg
reg   = 1
  r-from   r-to    area
    105     106    {cross_area:.6f}
part  = photon
output = flux
e-type = 3
ne    = {cross_ne}
emin  = {cross_emin:.6f}
emax  = {cross_emax:.6f}
axis  = eng
unit  = 1
file  = cross_spectrum_{mat}_{energy_kev}keV.out
"""


def build_input(mat: str, energy_kev: float, thickness_cm: float) -> str:
    energy_kev = int(round(energy_kev))
    e0_mev = energy_kev / 1000.0
    comp_lines = "\n      ".join(f"{za}  {wt}" for za, wt in COMPOSITION[mat].items())
    z_sample_back = Z_COLLIM1_BACK + thickness_cm
    z_c2b = z_sample_back + COLLIM2_LEN
    z_det_back = z_c2b + DET_LEN
    z_outer = z_det_back + Z_OUTER_MARGIN  # bien ngoai cach dau do 1 khoang du de tia tan xa khong bi cat

    emin_peak = PEAK_FRACTION * e0_mev
    cross_emax = CROSS_EMAX_FACTOR * e0_mev
    cross_emin = min(CROSS_EMIN_ABS, CROSS_EMIN_FRACTION * e0_mev)

    return TEMPLATE.format(
        mat=mat, mat_upper=mat.upper(), energy_kev=energy_kev,
        e0_mev=e0_mev,
        source_r0=SOURCE_R0,
        mat_comp=comp_lines,
        z_c1f=Z_COLLIM1_FRONT, z_c1b=Z_COLLIM1_BACK,
        z_sample_back=z_sample_back, z_c2b=z_c2b, z_det_back=z_det_back,
        z_outer=z_outer,
        hole_radius=HOLE_RADIUS,
        density=DENSITY[mat],
        ne_peak=NE_PEAK,
        emin_peak=emin_peak,
        cross_area=CROSS_AREA,
        cross_ne=CROSS_NE,
        cross_emin=cross_emin,
        cross_emax=cross_emax,
    )


BLANK_TEMPLATE = """Narrow Beam Gamma Shielding - BLANK (no sample) @ {energy_kev} keV

[ Parameters ]
icntl    = 0
nucdata  = 0
maxcas   = 1000000
maxbch   = 1
file(6)  = phits_blank_{energy_kev}keV.out

[ Source ]
totfact  = 1.0
s-type   = 1
x0       = 0.0
y0       = 0.0
z0       = 0.0
z1       = 0.0
proj     = photon
e0       = {e0_mev:.6f}
dir      = 1
r0       = {source_r0}

[ Material ]
m1    82000.00c  1.0

m2    5000.00c  -0.0620
      8000.00c  -0.2752
      14000.00c  -0.0179
      20000.00c  -0.0255
      57000.00c  -0.6195

m3    11000.00c  -0.153
      53000.00c  -0.847

[ Surface ]
10  pz   {z_c1f}
11  pz   {z_c1b}
12  pz   {z_sample_back:.4f}
13  pz   {z_c2b:.4f}
14  pz   {z_det_back:.4f}
15  pz   0.0
24  pz  -5.0
25  pz  {z_outer:.4f}

20  cz   {hole_radius}
21  cz   1.0
22  cz   2.5
23  cz   5.0
99  so 100.0

[ Cell ]
101   1 -11.34   10 -11 -21 20
102   0          10 -11 -20
103   0          11 -12 -22
104   1 -11.34   12 -13 -21 20
105   0          12 -13 -20
106   3 -3.67    13 -14 -23
110   0          -99 #101 #102 #103 #104 #105 #106
111  -1          99

[ Volume ]
reg   vol
106   392.7

[ T-Track ]
title = Total fluence of Photons in Detector (blank)
mesh  = reg
reg   = 106
part  = photon
e-type = 2
ne    = 1
emin  = 0.0
emax  = {e0_mev:.6f}
unit  = 1
axis  = reg
file  = flux_total_blank_{energy_kev}keV.out

[ T-Track ]
title = Fluence spectrum near peak (blank, for uncollided extraction)
mesh  = reg
reg   = 106
part  = photon
e-type = 2
ne    = {ne_peak}
emin  = {emin_peak:.6f}
emax  = {e0_mev:.6f}
unit  = 1
axis  = eng
file  = flux_spectrum_blank_{energy_kev}keV.out

[ T-Cross ]
title = Fluence crossing detector entrance face (blank, T-Cross method, kieu FLUKA USRBDX)
mesh  = reg
reg   = 1
  r-from   r-to    area
    105     106    {cross_area:.6f}
part  = photon
output = flux
e-type = 3
ne    = {cross_ne}
emin  = {cross_emin:.6f}
emax  = {cross_emax:.6f}
axis  = eng
unit  = 1
file  = cross_spectrum_blank_{energy_kev}keV.out
"""

REFERENCE_THICKNESS = 0.5  # cm - khong anh huong flux blank (chum song song, khong suy giam trong chan khong)


def build_blank_input(energy_kev) -> str:
    energy_kev = int(round(energy_kev))
    e0_mev = energy_kev / 1000.0
    z_sample_back = Z_COLLIM1_BACK + REFERENCE_THICKNESS
    z_c2b = z_sample_back + COLLIM2_LEN
    z_det_back = z_c2b + DET_LEN
    z_outer = z_det_back + Z_OUTER_MARGIN

    emin_peak = PEAK_FRACTION * e0_mev
    cross_emax = CROSS_EMAX_FACTOR * e0_mev
    cross_emin = min(CROSS_EMIN_ABS, CROSS_EMIN_FRACTION * e0_mev)

    return BLANK_TEMPLATE.format(
        energy_kev=energy_kev, e0_mev=e0_mev,
        source_r0=SOURCE_R0,
        z_c1f=Z_COLLIM1_FRONT, z_c1b=Z_COLLIM1_BACK,
        z_sample_back=z_sample_back, z_c2b=z_c2b, z_det_back=z_det_back,
        z_outer=z_outer,
        hole_radius=HOLE_RADIUS,
        ne_peak=NE_PEAK,
        emin_peak=emin_peak,
        cross_area=CROSS_AREA,
        cross_ne=CROSS_NE,
        cross_emin=cross_emin,
        cross_emax=cross_emax,
    )


def main(excel_path: str, out_dir: str):
    df = pd.read_excel(excel_path)
    materials = [c for c in df.columns if c.lower() != "energy" and c.lower() != "s0"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for _, row in df.iterrows():
        energy_kev = row["Energy"]

        # 1 job blank / nang luong, dung chung cho ca 6 vat lieu
        blank_name = f"blank_{int(round(energy_kev))}keV"
        blank_dir = out_dir / blank_name
        blank_dir.mkdir(parents=True, exist_ok=True)
        (blank_dir / f"{blank_name}.inp").write_text(build_blank_input(energy_kev))
        count += 1

        for mat in materials:
            thickness = row[mat]
            content = build_input(mat, energy_kev, thickness)
            job_name = f"{mat}_{int(round(energy_kev))}keV"
            job_dir = out_dir / job_name
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / f"{job_name}.inp").write_text(content)
            count += 1

    print(f"Da sinh {count} job (moi job 1 thu muc rieng) trong '{out_dir}' "
          f"({len(df)} muc nang luong x (6 vat lieu + 1 blank))")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    elif Path("data.xlsx").exists():
        excel_path = "data.xlsx"
    else:
        excel_path = "thickness_table.xlsx"

    out_dir = sys.argv[2] if len(sys.argv) > 2 else "inputs"
    main(excel_path, out_dir)

