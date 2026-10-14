"""
Sinh tu dong file .inp cho PHITS tu bang be day (Energy x s1..s6) trong Excel.
Chay: python generate_inputs.py thickness_table.xlsx inputs/

Moi job gio chi con 3 tally T-Interact (khong con T-Track / T-Cross):
  1) Compton (incoherent)  interaction spectrum trong vung mau (region 103)
  2) Photoelectric         interaction spectrum trong vung mau (region 103)
  3) Pair production       interaction spectrum trong vung mau (region 103)
     (chi != 0 khi e0 >= 1.022 MeV, nhung van giu de dung chung cho moi muc
      nang luong neu sau nay khao sat them muc >= 1.022 MeV)

Cong thuc tinh he so R (dung buildup):
    R = mu_compton / (mu_total - mu_rayleigh)
      = mu_compton / (mu_compton + mu_photoelec + mu_pairprod)
=> chi can 3 tally T-Interact tren la du, khong can T-Track/T-Cross doc flux nua,
   va cung khong can chay job "blank" (khong mau) de doi chieu.
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
HOLE_RADIUS = 0.25           # khop voi surface 20 = cz 0.25 (theo file .inp chuan)

# Tham so tally T-Interact (do interaction ngay trong vung mau, region 103)
INTERACT_NE = 100                  # so bin nang luong (log/linear tuy e-type)
INTERACT_EMIN_ABS = 0.001          # MeV, tran tren cho emin (khong vuot qua 1 keV)
INTERACT_EMIN_FRACTION = 0.1       # emin khong vuot qua 10% cua e0 (tranh emin>=emax
                                    # khi e0 rat thap, vi du 1-50 keV trong seri quet)
INTERACT_EMAX_FACTOR = 1.1         # emax = 1.1 * e0 (du du de bat het dinh nang luong)

# Nguong cutoff electron emin(12): TANG theo e0 de giam thoi gian track cascade
# o job nang luong cao (vai MeV tro len electron/positron sinh ra co dong nang
# lon, EGS5 phai mat rat nhieu buoc nho de "tha doc" xuong cutoff cu 0.1 MeV
# co dinh -> cham). Vi tally T-Interact chi ghi nhan tuong tac cua PHOTON tai
# thoi diem xay ra (khong phu thuoc electron sinh ra sau do duoc theo doi tiep
# hay dung som), nen nang cutoff nay AN TOAN, khong lam sai R.
ELECTRON_CUTOFF_MIN = 0.1          # MeV, san (khop muc cu, dung cho e0 thap)
ELECTRON_CUTOFF_FRACTION = 0.2     # cutoff = 20% cua e0
ELECTRON_CUTOFF_MAX = 3.0          # MeV, tran tren - nang len de cac muc rat cao
                                    # (5000-15000 keV) cung duoc tang cutoff them,
                                    # khong bi dung tran som o 1.0 MeV nhu truoc

# So history (maxcas): GIAM dan o vung nang luong cao. Ly do thuc su gay cham
# o vung nay KHONG PHAI do buoc track electron dai (emin(12) da xu ly), ma do
# "electromagnetic shower": moi electron/positron sinh ra van phat bremsstrahlung
# va positron van huy cap sinh 2 photon 511 keV - CAC PHOTON CON NAY lai duoc
# PHITS transport day du (co the Compton/quang dien tiep). So luot tuong tac
# thu cap tang manh theo nang luong nguon, khong lien quan gi den cutoff
# electron. Giam maxcas la cach truc tiep nhat de kiem soat thoi gian chay,
# danh doi lay sai so thong ke lon hon (kiem tra qua r.err trong file .out).
MAXCAS_TIERS = [
    # (nguong e0 duoi, MeV):  maxcas
    (1.0,   1_000_000),   # e0 < 1 MeV: giu nguyen, da chay OK
    (5.0,     300_000),   # 1 <= e0 < 5 MeV
    (10.0,    150_000),   # 5 <= e0 < 10 MeV
    (float("inf"), 100_000),  # e0 >= 10 MeV
]


def get_maxcas(e0_mev: float) -> int:
    for upper, maxcas in MAXCAS_TIERS:
        if e0_mev < upper:
            return maxcas
    return MAXCAS_TIERS[-1][1]


# So luong OpenMP (bien "$OMP=" phits.sh doc truc tiep tu dong dau file .inp,
# truoc section [ Parameters ] dau tien). OMP=1 nghia la chay 1 luong nhu binh
# thuong (khong doi so voi truoc). OMP>=2 -> phits.sh tu export OMP_NUM_THREADS
# va chay bang phits_omp_lin, cho 1 job dung nhieu core CUNG LUC - day la cach
# tang toc THAT SU (khong danh doi do chinh xac), khac voi giam maxcas o tren.
# CHI dat OMP cao cho job nang luong cao (buildup shower nang) vi job nang
# luong thap da chay du nhanh voi 1 luong, khong can them.
OMP_THREADS_TIERS = [
    # (nguong e0 duoi, MeV):  so luong OpenMP
    (1.0,  1),     # e0 < 1 MeV: giu nguyen 1 luong (da du nhanh)
    (5.0,  4),     # 1 <= e0 < 5 MeV
    (10.0, 8),     # 5 <= e0 < 10 MeV
    (float("inf"), 8),  # e0 >= 10 MeV
]


def get_omp_threads(e0_mev: float) -> int:
    for upper, threads in OMP_THREADS_TIERS:
        if e0_mev < upper:
            return threads
    return OMP_THREADS_TIERS[-1][1]


TEMPLATE = """Narrow Beam Gamma Shielding - Material {mat_upper} @ {energy_kev} keV - tinh R

$OMP={omp_threads}

[ Parameters ]
icntl    = 0
nucdata  = 0
maxcas   = {maxcas}
maxbch   = 1
negs     = 1        $ BAT BUOC: bat EGS5 de dung T-Interact
emin(14) = 1.0e-3   $ nguong cutoff photon (MeV)
emin(12) = {electron_cutoff:.6f}   $ nguong cutoff electron (MeV) - tang theo e0 de giam thoi gian
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
103   2 -{density}  11 -12 -22   $ vung mau {mat_upper} - can tinh R o day
104   1 -11.34   12 -13 -21 20
105   0          12 -13 -20
106   3 -3.67    13 -14 -23
110   0          -99 #101 #102 #103 #104 #105 #106
111  -1          99

$ ===================================================================
$ Cong thuc: R = mu_compton / (mu_total - mu_rayleigh)
$          = mu_compton / (mu_compton + mu_photoelec + mu_pairprod)
$ (vi mu_total - mu_rayleigh = tong tat ca thanh phan TRU rayleigh
$  = compton + photoelec + pairprod)
$ => CAN 3 tally duoi day (compton, photoelec, pairprod).
$    LUU Y: pairprod chi = 0 khi nguon < 1.022 MeV (nguong tao cap).
$    Neu ban khao sat nhieu muc nang luong (co muc >= 1.022 MeV),
$    BAT BUOC phai giu tally pairprod nay, khong duoc bo qua.
$ ===================================================================

[ T-Interact ]
title  = Compton (incoherent) interaction spectrum in {mat_upper} sample (region 103)
mesh   = reg
reg    = 103
part   = photon
e-type = 2
ne     = {interact_ne}
emin   = {interact_emin:.6f}
emax   = {interact_emax:.6f}
unit   = 1
axis   = eng
output = compton
file   = interact_compton_{mat}_{energy_kev}keV.out
epsout = 1

[ T-Interact ]
title  = Photoelectric interaction spectrum in {mat_upper} sample (region 103)
mesh   = reg
reg    = 103
part   = photon
e-type = 2
ne     = {interact_ne}
emin   = {interact_emin:.6f}
emax   = {interact_emax:.6f}
unit   = 1
axis   = eng
output = photoelec
file   = interact_photoelec_{mat}_{energy_kev}keV.out
epsout = 1

[ T-Interact ]
title  = Pair production interaction spectrum in {mat_upper} sample (region 103) - GIU LAI vi co khao sat nhieu muc nang luong
mesh   = reg
reg    = 103
part   = photon
e-type = 2
ne     = {interact_ne}
emin   = {interact_emin:.6f}
emax   = {interact_emax:.6f}
unit   = 1
axis   = eng
output = pairprod
file   = interact_pairprod_{mat}_{energy_kev}keV.out
epsout = 1

[End]
"""


def build_input(mat: str, energy_kev: float, thickness_cm: float) -> str:
    energy_kev = int(round(energy_kev))
    e0_mev = energy_kev / 1000.0
    comp_lines = "\n      ".join(f"{za}  {wt}" for za, wt in COMPOSITION[mat].items())
    z_sample_back = Z_COLLIM1_BACK + thickness_cm
    z_c2b = z_sample_back + COLLIM2_LEN
    z_det_back = z_c2b + DET_LEN
    z_outer = z_det_back + Z_OUTER_MARGIN  # bien ngoai cach dau do 1 khoang du de tia tan xa khong bi cat

    interact_emax = INTERACT_EMAX_FACTOR * e0_mev
    interact_emin = min(INTERACT_EMIN_ABS, INTERACT_EMIN_FRACTION * e0_mev)
    electron_cutoff = min(ELECTRON_CUTOFF_MAX, max(ELECTRON_CUTOFF_MIN, ELECTRON_CUTOFF_FRACTION * e0_mev))
    maxcas = get_maxcas(e0_mev)
    omp_threads = get_omp_threads(e0_mev)

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
        interact_ne=INTERACT_NE,
        interact_emin=interact_emin,
        interact_emax=interact_emax,
        electron_cutoff=electron_cutoff,
        maxcas=maxcas,
        omp_threads=omp_threads,
    )


def main(excel_path: str, out_dir: str):
    df = pd.read_excel(excel_path)
    materials = [c for c in df.columns if c.lower() != "energy"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for _, row in df.iterrows():
        energy_kev = row["Energy"]

        for mat in materials:
            thickness = row[mat]
            content = build_input(mat, energy_kev, thickness)
            job_name = f"{mat}_{int(round(energy_kev))}keV"
            job_dir = out_dir / job_name
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / f"{job_name}.inp").write_text(content)
            count += 1

    print(f"Da sinh {count} job (moi job 1 thu muc rieng) trong '{out_dir}' "
          f"({len(df)} muc nang luong x {len(materials)} vat lieu)")


if __name__ == "__main__":
    excel_path = sys.argv[1] if len(sys.argv) > 1 else "thickness_table.xlsx"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "inputs"
    main(excel_path, out_dir)
