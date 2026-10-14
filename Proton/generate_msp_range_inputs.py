"""
Sinh tu dong file .inp PHITS de tinh MSP(entrance) va Projected Range cho
PROTON trong CA 6 VAT LIEU (s1..s6), dai nang luong 15 keV - 15000 keV (15 MeV).

Khac voi generate_inputs.py (bai toan truyen qua tam chan gamma), o day:
  - Khong can chay "blank" (khong co collimator/detector, chi 1 khoi vat lieu don gian)
  - Hinh hoc don gian: 1 khoi vat lieu day zmax, chum tia ban thang vao theo truc z
  - 2 tally: [T-Deposit] (Bragg curve -> MSP) va [T-Track] theo z (flux profile -> range)
  - Mesh (zmax, nz) PHAI thay doi theo tung nang luong VA tung vat lieu vi range
    bien thien vai bac do lon (~vai chuc nm o 15 keV den ~vai tram um o 15 MeV,
    va khac nhau giua 6 vat lieu do mat do khac nhau). Script tu dong chon mesh
    dua tren bang range SRIM da co (chi co cho 1 vat lieu tham chieu,
    SRIM_TABLE_MATERIAL = "s6") roi SCALE THEO TY LE MAT DO cho 5 vat lieu con
    lai (xem estimate_range_for_material()) + he so an toan.

Cach dung:
  1. Chuan bi file srim_range_table.csv (tu bang SRIM proton cho s6 da co san):
       energy_keV, range_um
     Bao nhieu DONG trong file nay se sinh ra bay nhieu MUC NANG LUONG (nhan
     voi 6 vat lieu = tong so job). Gia tri range_um CHI dung THANG (khong
     noi suy) cho vat lieu s6 (vi la gia tri SRIM that); cho 5 vat lieu con
     lai, gia tri nay duoc SCALE theo ty le mat do de uoc luong mesh (KHONG
     phai gia tri range chinh xac cua 5 vat lieu do - range chinh xac se
     duoc TU TINH RA tu chinh ket qua PHITS sau nay bang script phan tich
     rieng, khong phu thuoc vao uoc luong nay).
  2. Chay: python generate_msp_range_inputs.py srim_range_table.csv inputs_msp_range/

  (Ham default_energy_list_kev()/ENERGY_LIST_KEV/loglog_interp() van con trong
  file de tham khao/du phong - vi du neu ban muon tu sinh mot dai nang luong
  log-space rieng khong khop voi bang SRIM - nhung KHONG duoc goi trong luong
  chay mac dinh nua.)

Sau khi chay PHITS xong, dung script phan tich rieng (parse_msp_range.py) de
tinh MSP(entrance) va Projected Range cho tung vat lieu tu ket qua T-Deposit/
T-Track that (khong phu thuoc vao gia tri uoc luong scale o tren).
"""
import math
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Thanh phan vat lieu (wt fraction, am = weight fraction theo PHITS) va mat do
# cho CA 6 VAT LIEU s1..s6 - dung chung file alpha truoc
# ---------------------------------------------------------------------------
COMPOSITION = {
    "s1": {"5000.00c": -0.1629, "8000.00c": -0.4648, "14000.00c": -0.0302, "20000.00c": -0.0431, "57000.00c": -0.2990},
    "s2": {"5000.00c": -0.1329, "8000.00c": -0.4086, "14000.00c": -0.0266, "20000.00c": -0.0379, "57000.00c": -0.3941},
    "s3": {"5000.00c": -0.1095, "8000.00c": -0.3644, "14000.00c": -0.0237, "20000.00c": -0.0338, "57000.00c": -0.4688},
    "s4": {"5000.00c": -0.0905, "8000.00c": -0.3289, "14000.00c": -0.0214, "20000.00c": -0.0305, "57000.00c": -0.5288},
    "s5": {"5000.00c": -0.0750, "8000.00c": -0.2996, "14000.00c": -0.0195, "20000.00c": -0.0278, "57000.00c": -0.5783},
    "s6": {"5000.00c": -0.0620, "8000.00c": -0.2752, "14000.00c": -0.0179, "20000.00c": -0.0255, "57000.00c": -0.6195},
}
DENSITY = {"s1": 3.0099, "s2": 3.1999, "s3": 3.3899, "s4": 3.5799, "s5": 3.7699, "s6": 3.9599}  # g/cm3

# Vat lieu ma bang srim_range_table.csv dang co san (range THAT tu SRIM).
# Cac vat lieu con lai se UOC LUONG range bang cach scale theo ty le mat do
# so voi vat lieu nay (xem giai thich o estimate_range_for_material() ben duoi).
SRIM_TABLE_MATERIAL = "s6"

# ---------------------------------------------------------------------------
# Thong so hat toi (mac dinh proton). A = so khoi, dung de doi don vi
# nang luong sang MeV/n theo quy uoc nguon ion cua PHITS (voi proton A=1
# nen MeV/n = MeV toan phan, khong doi gi ca).
# ---------------------------------------------------------------------------
PROJECTILE = "proton"
MASS_NUMBER_A = 1

# ---------------------------------------------------------------------------
# Dai nang luong mac dinh (CHI DUNG KHI KHONG CO BANG SRIM / --log-spaced):
# log-spaced 15 keV - 15000 keV. Mac dinh script se doc thang danh sach nang
# luong TU CHINH BANG SRIM (srim_range_table.csv) thay vi dung list nay,
# xem ham load_energy_list_from_table() va main() ben duoi.
# ---------------------------------------------------------------------------
def default_energy_list_kev(n_points=25):
    e_min, e_max = 15.0, 15000.0
    log_min, log_max = math.log10(e_min), math.log10(e_max)
    return [
        round(10 ** (log_min + i * (log_max - log_min) / (n_points - 1)), 3)
        for i in range(n_points)
    ]


ENERGY_LIST_KEV = default_energy_list_kev()

# ---------------------------------------------------------------------------
# Tham so mesh
# ---------------------------------------------------------------------------
NZ_BINS = 300          # so lop z co dinh cho moi nang luong (do phan giai tuong doi ~const)
SAFETY_MARGIN = 1.6    # zmax = SAFETY_MARGIN * range_uoc_luong_tu_SRIM
MIN_ZMAX_CM = 2.0e-7   # san toi thieu (2 nm) de tranh mesh qua nho o nang luong rat thap
BEAM_RADIUS_CM = 0.02  # r0 nguon, khop template alpha truoc

TEMPLATE = """MSP + Range Profile - {proj} in Glass {mat_upper} @ {energy_kev:g} keV

$OMP=4

[ Parameters ]
icntl    = 0
nucdata  = 0
maxcas   = 1000000
maxbch   = 1
file(6)  = phits_msp_{proj}_{mat}_{energy_tag}.out

[ Source ]
totfact  = 1.0
s-type   = 1
x0       = 0.0
y0       = 0.0
z0       = 0.0
z1       = 0.0
proj     = {proj}
e0       = {e0_per_nucleon:.6f}  $ MeV/n -> tong dong nang = {e0_per_nucleon:.6f}*{A} = {energy_mev:.6f} MeV = {energy_kev:g} keV
dir      = 1
r0       = {beam_radius}

[ Material ]
m2    {mat_comp}

[ Surface ]
10  pz   0.0
11  pz   {zmax:.10f}     $ be day khoi = {zmax_um:.4f} um (= {safety}x range uoc luong SRIM {range_um:.4f} um)
20  cz   1.0
99  so  100.0

[ Cell ]
101   2 -{density}   10 -11 -20
102   0              -99 #101
103  -1              99

[ T-Deposit ]
title  = Depth-dose profile (Bragg curve) - dung de suy ra MSP(E)
mesh   = xyz
x-type = 2
nx     = 1
xmin   = -1.0
xmax   =  1.0
y-type = 2
ny     = 1
ymin   = -1.0
ymax   =  1.0
z-type = 2
nz     = {nz}          $ moi lop day {dz_um:.6f} um - PHAI KHOP voi T-Track ben duoi
zmin   = 0.0
zmax   = {zmax:.10f}
unit   = 2          $ MeV/source (nang luong hap thu TRONG TUNG LOP)
axis   = z
output = dose
letmat = 0
part   = {proj}
file   = dose_profile_{proj}_{mat}_{energy_tag}.out

[ T-Track ]
title  = Depth-fluence profile (doc ra Projected Range bang tich phan duong cong flux)
mesh   = xyz
x-type = 2
nx     = 1
xmin   = -1.0
xmax   =  1.0
y-type = 2
ny     = 1
ymin   = -1.0
ymax   =  1.0
z-type = 2
nz     = {nz}
zmin   = 0.0
zmax   = {zmax:.10f}
part   = {proj}
e-type = 2
ne     = 1
emin   = 0.0
emax   = {energy_mev:.6f}
unit   = 1
axis   = z
file   = range_profile_{proj}_{mat}_{energy_tag}.out
"""


def loglog_interp(x_target, xs, ys):
    """Noi suy log-log tuyen tinh, ngoai suy canh bao neu ngoai khoang bang."""
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    lt = math.log(x_target)

    if lt <= lx[0]:
        i0, i1 = 0, 1
        print(f"  [canh bao] {x_target:g} keV nam duoi bang SRIM, dang ngoai suy", file=sys.stderr)
    elif lt >= lx[-1]:
        i0, i1 = len(lx) - 2, len(lx) - 1
        print(f"  [canh bao] {x_target:g} keV nam tren bang SRIM, dang ngoai suy", file=sys.stderr)
    else:
        i1 = next(i for i, v in enumerate(lx) if v >= lt)
        i0 = i1 - 1

    frac = (lt - lx[i0]) / (lx[i1] - lx[i0])
    ly_t = ly[i0] + frac * (ly[i1] - ly[i0])
    return math.exp(ly_t)


def load_srim_range_table(path):
    import csv
    xs, ys = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            xs.append(float(row["energy_keV"]))
            ys.append(float(row["range_um"]))
    pairs = sorted(zip(xs, ys))
    xs, ys = zip(*pairs)
    return list(xs), list(ys)


def estimate_range_for_material(material: str, range_um_srim_table: float) -> float:
    """
    Bang srim_range_table.csv chi co range THAT cho MOT vat lieu tham chieu
    (SRIM_TABLE_MATERIAL, mac dinh s6). Cac vat lieu con lai (s1..s5) KHONG
    co bang SRIM rieng, nen phai UOC LUONG range bang cach scale theo ty le
    mat do so voi vat lieu tham chieu:

        range_uoc_luong(mat) = range_srim(mat_tham_chieu) * mat_do(mat_tham_chieu) / mat_do(mat)

    Ly do: voi cung 1 chum proton, vat lieu CANG NHE (mat do thap) thi
    proton di duoc CANG XA (range lon hon), xap xi ty le nghich voi mat do
    (dung cho cac vat lieu co thanh phan nguyen to tuong tu nhau, nhu day la
    cung 1 he thuy tinh B-O-Si-Ca-La chi doi ty le). Day CHI LA UOC LUONG DE
    CHON MESH (zmax) DU RONG, KHONG PHAI gia tri range chinh xac - gia tri
    range chinh xac se duoc TU TINH RA TU KET QUA PHITS (T-Track) sau nay,
    khong phu thuoc vao uoc luong nay.

    Neu material == SRIM_TABLE_MATERIAL thi tra ve dung gia tri bang SRIM
    (khong scale).
    """
    if material == SRIM_TABLE_MATERIAL:
        return range_um_srim_table
    return range_um_srim_table * DENSITY[SRIM_TABLE_MATERIAL] / DENSITY[material]


def build_input(material: str, energy_kev: float, range_um_estimate: float) -> str:
    energy_mev = energy_kev / 1000.0
    e0_per_nucleon = energy_mev / MASS_NUMBER_A

    zmax_cm = max(SAFETY_MARGIN * range_um_estimate * 1e-4, MIN_ZMAX_CM)
    zmax_um = zmax_cm * 1e4
    dz_um = zmax_um / NZ_BINS

    comp_lines = "\n      ".join(f"{za}  {wt}" for za, wt in COMPOSITION[material].items())
    energy_tag = f"{energy_kev:g}keV".replace(".", "p")

    return TEMPLATE.format(
        proj=PROJECTILE,
        A=MASS_NUMBER_A,
        mat=material,
        mat_upper=material.upper(),
        energy_kev=energy_kev,
        energy_mev=energy_mev,
        e0_per_nucleon=e0_per_nucleon,
        beam_radius=BEAM_RADIUS_CM,
        mat_comp=comp_lines,
        density=DENSITY[material],
        zmax=zmax_cm,
        zmax_um=zmax_um,
        range_um=range_um_estimate,
        safety=SAFETY_MARGIN,
        nz=NZ_BINS,
        dz_um=dz_um,
        energy_tag=energy_tag,
    )


def main(srim_range_csv: str, out_dir: str):
    xs, ys = load_srim_range_table(srim_range_csv)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Dung DUNG cac muc nang luong da khai bao trong bang SRIM (xs) lam
    # ENERGY_LIST_KEV cho batch nay -> bao nhieu dong trong bang SRIM se
    # sinh ra bay nhieu job (nhan voi so vat lieu). Gia tri range (ys) la
    # gia tri SRIM THAT cho vat lieu SRIM_TABLE_MATERIAL; cac vat lieu con
    # lai duoc scale qua estimate_range_for_material().
    count = 0
    for material in COMPOSITION:
        for energy_kev, range_um_srim in zip(xs, ys):
            range_um_est = estimate_range_for_material(material, range_um_srim)
            content = build_input(material, energy_kev, range_um_est)

            energy_tag = f"{energy_kev:g}keV".replace(".", "p")
            job_name = f"{PROJECTILE}_{material}_{energy_tag}"
            job_dir = out_dir / job_name
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / f"{job_name}.inp").write_text(content)
            count += 1
            tag = "SRIM that" if material == SRIM_TABLE_MATERIAL else f"uoc luong (scale tu {SRIM_TABLE_MATERIAL})"
            print(f"  [{material}] {energy_kev:>9.2f} keV -> zmax={SAFETY_MARGIN*range_um_est:.4f} um "
                  f"(range {tag} {range_um_est:.4f} um), nz={NZ_BINS}")

    print(f"\nDa sinh {count} job ({len(COMPOSITION)} vat lieu x {len(xs)} nang luong) "
          f"trong '{out_dir}'")


if __name__ == "__main__":
    srim_csv = sys.argv[1] if len(sys.argv) > 1 else "srim_range_table.csv"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "inputs_msp_range"
    main(srim_csv, out_dir)
