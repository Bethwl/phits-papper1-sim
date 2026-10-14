"""
Doc ket qua T-Deposit (Bragg curve) + T-Track (depth-fluence profile) tu file
.out cua PHITS (dinh dang ANGEL), tinh MSP(entrance) va Projected Range cho
TUNG VAT LIEU (s1..s6) x TUNG NANG LUONG, xuat ra Excel theo layout
Energy x s1..s6 (giong dung layout cac script parse_results.py truoc day).

Cau truc thu muc ky vong (moi vat lieu x nang luong la 1 thu muc rieng,
gia dinh generate_msp_range_inputs_alpha.py da duoc chay rieng cho tung vat
lieu s1..s6, dat ten thu muc theo dung mau alpha_{mat}_{energy}keV):
    outputs_msp_range_alpha/alpha_s1_15keV/dose_profile_alpha_s1_15keV.out
    outputs_msp_range_alpha/alpha_s1_15keV/range_profile_alpha_s1_15keV.out
    outputs_msp_range_alpha/alpha_s2_15keV/dose_profile_alpha_s2_15keV.out
    ...
    outputs_msp_range_alpha/alpha_s6_15keV/dose_profile_alpha_s6_15keV.out

NEU thu muc job cua ban dat ten KHAC mau nay (vi du khong co tien to
"proton_"), sua lai ham job_name_for() ben duoi cho khop.

File Excel dau vao: cot dau "Energy" (hoac "energy_keV"), cac cot con lai
la TEN VAT LIEU (s1, s2, ..., s6) - GIONG HET cau truc thickness_table.xlsx
da dung trong parse_results.py truoc day. Gia tri trong cac cot vat lieu
KHONG duoc dung (chi dung TEN COT de biet co nhung vat lieu nao).

QUAN TRONG - mat do rieng cho tung vat lieu: MSP = dE/dx / mat do, nen PHAI
biet dung mat do cua TUNG vat lieu. Khai bao trong DENSITY_TABLE_G_CM3 ben
duoi - PHAI SUA LAI cho khop voi tung vat lieu s1..s6 cua ban (hien chi co
s6 = 3.9599 g/cm3 la biet chac, cac vat lieu con lai dang de trong (None) -
BAT BUOC dien vao truoc khi chay, neu khong script se bao loi ro rang).

Cong thuc dung (xem chu thich chi tiet trong generate_msp_range_inputs.py):
  - MSP(entrance) = (nang luong hap thu O LOP DAU TIEN, MeV/source)
                    / (be day lop dau tien, cm)
                    / mat do vat lieu (g/cm3)
                    -> don vi MeV.cm2/g
    LUU Y: day chi la GAN DUNG tu 1 lan chay duy nhat (lay nguyen lop dau
    tien sat be mat), khong phai ngoai suy Delta_z -> 0.

  - Goi flux(z) la gia tri T-Track doc duoc (unit=1, 1/cm2/source) tai moi
    lop z, thi ham song sot Pr(Range > z) = flux(z) * A_MESH_CM2 (xem giai
    thich A_MESH_CM2 ben duoi). Projected Range:
        R = tich phan [flux(z) * A_MESH_CM2] dz          (0 -> zmax)
    Tich phan duoc roi rac hoa bang tong Riemann tren tung lop mesh (dz_i
    lay tu chinh z-lower/z-upper doc duoc trong file, khong gia dinh dz
    co dinh).

  KHONG con tinh Straggling nua (theo yeu cau - bo qua, chi lay MSP + Range).

Chay: python parse_msp_range_alpha.py thickness_table.xlsx outputs_msp_range_alpha/ msp_range_results_alpha.xlsx
"""
import sys
import pandas as pd
from pathlib import Path

PROJECTILE = "alpha"  # PHAI khop voi PROJECTILE trong generate_msp_range_inputs_alpha.py
                       # (ten thu muc job la {PROJECTILE}_{mat}_{energy}keV)

# ---------------------------------------------------------------------------
# BAT BUOC KHAI BAO DUNG mat do (g/cm3) cho TUNG vat lieu s1..s6 truoc khi
# chay. Neu vat lieu nao con de None, script se bao loi ro rang thay vi tu
# doan sai.
# ---------------------------------------------------------------------------
DENSITY_TABLE_G_CM3 = {
    "s1": 3.0099,
    "s2": 3.1999,
    "s3": 3.3899,
    "s4": 3.5799,
    "s5": 3.7699,
    "s6": 3.9599,
}

# ---------------------------------------------------------------------------
# QUAN TRONG - he so chuan hoa dien tich mesh x-y cua tally [T-Track]:
# Trong file .inp, mesh [T-Track] khai bao:
#     x-type=2  nx=1  xmin=-1.0  xmax=1.0
#     y-type=2  ny=1  ymin=-1.0  ymax=1.0
# => dien tich mat cat ngang mesh A_MESH = (xmax-xmin)*(ymax-ymin) = 2*2 = 4 cm^2.
#
# PHITS tinh tally "flux" (unit=1) bang cach CHIA cho THE TICH cua mesh
# (bao gom ca dien tich x-y nay), trong khi chum tia proton (r0=0.02 cm) chi
# chiem 1 dien tich rat nho so voi 4 cm^2 do. Vi vay gia tri flux doc duoc
# tu file .out bi "loang" di dung bang A_MESH so voi ham song sot S(z) (gia
# tri nam trong [0,1]) ma cong thuc R = tich phan S(z) dz can dung.
#
# NEU BAN SUA lai xmin/xmax/ymin/ymax trong generate_msp_range_inputs.py,
# PHAI SUA LAI hang so nay cho khop.
# ---------------------------------------------------------------------------
MESH_XMIN_CM, MESH_XMAX_CM = -1.0, 1.0
MESH_YMIN_CM, MESH_YMAX_CM = -1.0, 1.0
A_MESH_CM2 = (MESH_XMAX_CM - MESH_XMIN_CM) * (MESH_YMAX_CM - MESH_YMIN_CM)


def energy_tag_for(energy_kev: float) -> str:
    """Phai tao ra CHUOI GIONG HET generate_msp_range_inputs.py de khop ten thu muc job."""
    return f"{energy_kev:g}keV".replace(".", "p")


def job_name_for(material: str, energy_kev: float) -> str:
    """
    Ten thu muc job. Mac dinh gia dinh mau proton_{mat}_{energy}keV.
    SUA LAI ham nay neu thu muc job cua ban dat ten khac.
    """
    return f"{PROJECTILE}_{material}_{energy_tag_for(energy_kev)}"


def parse_profile(filepath: Path):
    """
    Doc file profile theo z (T-Deposit hoac T-Track, dinh dang ANGEL), tra ve
    danh sach tuple (z_lower_cm, z_upper_cm, value) cho TAT CA cac lop (can
    toan bo duong cong de tich phan Projected Range).

    Cot ap chot la r.err, cot ngay truoc la gia tri (dose hoac flux).
    """
    lines = filepath.read_text().splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and "lower" in stripped.lower() and "upper" in stripped.lower():
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Khong tim thay dong header profile trong {filepath}")

    data_rows = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            if data_rows:
                break  # het khoi du lieu (gap dong trong sau cac dong so)
            continue
        if stripped.startswith("#"):
            continue  # bo qua dong "# sum over ..." va cac dong comment khac
        parts = stripped.split()
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            continue
        if len(nums) >= 3:
            data_rows.append(nums)

    if not data_rows:
        raise ValueError(f"Khong doc duoc du lieu profile trong {filepath}")

    result = []
    for row in data_rows:
        z_lower, z_upper, value = row[0], row[1], row[-2]
        result.append((z_lower, z_upper, value))
    return result


def compute_msp_entrance(dose_rows, density_g_cm3: float) -> float:
    """
    MSP(entrance) tu T-Deposit: lay LOP DAU TIEN (gan z=0 nhat) co gia tri
    khac 0 (quet TU TREN XUONG, tu z=0 tang dan), chia cho be day lop (cm)
    va mat do (g/cm3) -> MeV.cm2/g.
    """
    for z_lower, z_upper, dose_mev in dose_rows:
        if dose_mev != 0:
            dz_cm = z_upper - z_lower
            if dz_cm <= 0:
                raise ValueError("Be day lop (dz) <= 0, du lieu profile khong hop le")
            dEdx_mev_per_cm = dose_mev / dz_cm
            return dEdx_mev_per_cm / density_g_cm3
    return 0.0


def compute_range(track_rows) -> float:
    """
    Tinh Projected Range (um) tu T-Track theo cong thuc:
        S_i = flux_i * A_MESH_CM2   (chuyen "flux" PHITS ve xac suat song sot)
        R   = sum( S_i * dz_i )
    voi dz_i = z_upper_i - z_lower_i. Tra ve range_um.
    """
    R_cm = 0.0
    for z_lower, z_upper, flux_val in track_rows:
        s_val = flux_val * A_MESH_CM2
        dz = z_upper - z_lower
        R_cm += s_val * dz
    return R_cm * 1e4


def find_energy_column(df: pd.DataFrame) -> str:
    for c in df.columns:
        if "energy" in c.lower():
            return c
    raise ValueError("Khong tim thay cot nang luong (ten cot phai chua 'energy') trong file dau vao")


def main(excel_path: str, outputs_dir: str, result_path: str):
    if excel_path.lower().endswith(".csv"):
        df = pd.read_csv(excel_path)
    else:
        df = pd.read_excel(excel_path)

    energy_col = find_energy_column(df)
    materials = [c for c in df.columns if c != energy_col]

    # Kiem tra mat do da khai bao du chua, bao loi RO RANG ngay tu dau
    # thay vi tinh sai roi moi phat hien sau.
    missing_density = [m for m in materials if DENSITY_TABLE_G_CM3.get(m) is None]
    if missing_density:
        raise ValueError(
            f"Chua khai bao mat do (g/cm3) cho cac vat lieu: {missing_density}. "
            f"Sua DENSITY_TABLE_G_CM3 o dau file parse_msp_range.py truoc khi chay."
        )

    outputs_dir = Path(outputs_dir)

    msp_result = df[[energy_col]].copy().rename(columns={energy_col: "Energy_keV"})
    range_result = df[[energy_col]].copy().rename(columns={energy_col: "Energy_keV"})
    for mat in materials:
        msp_result[mat] = None
        range_result[mat] = None

    missing = []
    parse_errors = []

    for idx, row in df.iterrows():
        energy_kev = float(row[energy_col])

        for mat in materials:
            job_name = job_name_for(mat, energy_kev)
            job_dir = outputs_dir / job_name

            dose_path = job_dir / f"dose_profile_{job_name}.out"
            range_path = job_dir / f"range_profile_{job_name}.out"

            if not dose_path.exists() or not range_path.exists():
                if not dose_path.exists():
                    missing.append(str(dose_path))
                if not range_path.exists():
                    missing.append(str(range_path))
                continue

            try:
                dose_rows = parse_profile(dose_path)
                track_rows = parse_profile(range_path)
                msp_entrance = compute_msp_entrance(dose_rows, DENSITY_TABLE_G_CM3[mat])
                range_um = compute_range(track_rows)
            except ValueError as e:
                parse_errors.append(f"{job_name}: {e}")
                continue

            msp_result.loc[idx, mat] = msp_entrance
            range_result.loc[idx, mat] = range_um

    with pd.ExcelWriter(result_path) as writer:
        msp_result.to_excel(writer, sheet_name="MSP_MeV_cm2_per_g", index=False)
        range_result.to_excel(writer, sheet_name="Projected_Range_um", index=False)

    print(f"Da luu ket qua vao '{result_path}' (2 sheet: MSP_MeV_cm2_per_g, Projected_Range_um)")

    if missing:
        print(f"\nCANH BAO: {len(missing)} file khong tim thay (bo qua):")
        for m in missing[:20]:
            print(" -", m)

    if parse_errors:
        print(f"\nCANH BAO: {len(parse_errors)} loi khi doc/tinh du lieu:")
        for e in parse_errors[:20]:
            print(" -", e)


if __name__ == "__main__":
    excel_path = sys.argv[1] if len(sys.argv) > 1 else "thickness_table.xlsx"
    outputs_dir = sys.argv[2] if len(sys.argv) > 2 else "outputs_msp_range_alpha"
    result_path = sys.argv[3] if len(sys.argv) > 3 else "msp_range_results_alpha.xlsx"
    main(excel_path, outputs_dir, result_path)
