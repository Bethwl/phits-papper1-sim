"""
Doc ket qua T-Interact tu file .out cua PHITS (dinh dang ANGEL), tinh he so
R = mu_compton / (mu_compton + mu_photoelec + mu_pairprod) cho tung
(vat lieu x nang luong), gom lai theo layout Energy x s1..s6, xuat ra Excel.

Cau truc thu muc (khop voi generate_inputs.py): moi job PHITS chay trong
MOT thu muc rieng, vi du:
    outputs/s1_80keV/interact_compton_s1_80keV.out
    outputs/s1_80keV/interact_photoelec_s1_80keV.out
    outputs/s1_80keV/interact_pairprod_s1_80keV.out

CHI LAY 1 SO DUY NHAT cho moi loai tuong tac: gia tri o BIN NANG LUONG CAO
NHAT co du lieu khac 0 - tuc mu(E0) tai dung nang luong nguon (giong cach
doc T-Cross truoc day, da kiem chung khop XCOM). KHONG cong don toan pho,
vi cac bin nang luong thap hon la do photon da tan xa (mat nang luong) roi
moi tuong tac tiep, khong thuoc ve mu(E0).

Cong thuc:
    R = mu_compton / (mu_total - mu_rayleigh)
      = compton_peak / (compton_peak + photoelec_peak + pairprod_peak)

Chay: python parse_results.py thickness_table.xlsx outputs/ R_results.xlsx
"""
import sys
import pandas as pd
from pathlib import Path


def parse_peak_bin(filepath: Path) -> float:
    """
    Doc file pho T-Interact (axis=eng), tra ve gia tri tuong tac (cot
    'compton'/'photoelec'/'pairprod') cua bin nang luong CAO NHAT co du
    lieu khac 0 - tuc muy(E0) tai dung nang luong nguon, DA KIEM CHUNG
    khop voi XCOM.

    Ly do khong duoc cong don toan pho: T-Interact ghi nhan nang luong cua
    photon TAI THOI DIEM no tuong tac. Photon chua tan xa (con nguyen E0)
    se roi vao bin sat dinh E0 nhat - day chinh la mu(E0) can lay. Cac bin
    nang luong thap hon la do photon DA tan xa (mat nang luong) roi moi
    tuong tac tiep - khong thuoc ve mu(E0), cong vao se lam sai R.

    Cach xu ly: quet TU DUOI LEN (tu bin nang luong cao nhat giam dan),
    gap dong DAU TIEN co gia tri khac 0 thi lay dong do (vi bin tren cung
    sat emax nhieu khi bang 0 do bien bin khong khop chinh xac voi e0).
    """
    lines = filepath.read_text().splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and "e-lower" in stripped.lower():
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Khong tim thay dong header pho trong {filepath}")

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
        if len(nums) >= 2:
            data_rows.append(nums)

    if not data_rows:
        raise ValueError(f"Khong doc duoc du lieu pho trong {filepath}")

    # Cot ap chot la r.err, cot truoc do la gia tri tuong tac
    for row in reversed(data_rows):
        val = row[-2]
        if val != 0:
            return val

    return 0.0


def main(excel_path: str, outputs_dir: str, result_path: str):
    df = pd.read_excel(excel_path)
    materials = [c for c in df.columns if c.lower() != "energy"]
    outputs_dir = Path(outputs_dir)

    result = df[["Energy"]].copy()
    for mat in materials:
        result[mat] = None

    missing = []
    parse_errors = []

    for idx, row in df.iterrows():
        energy_kev = int(round(row["Energy"]))

        for mat in materials:
            job_name = f"{mat}_{energy_kev}keV"
            job_dir = outputs_dir / job_name

            files = {
                "compton": job_dir / f"interact_compton_{job_name}.out",
                "photoelec": job_dir / f"interact_photoelec_{job_name}.out",
                "pairprod": job_dir / f"interact_pairprod_{job_name}.out",
            }

            missing_here = [str(p) for p in files.values() if not p.exists()]
            if missing_here:
                missing.extend(missing_here)
                continue

            try:
                compton_peak = parse_peak_bin(files["compton"])
                photoelec_peak = parse_peak_bin(files["photoelec"])
                pairprod_peak = parse_peak_bin(files["pairprod"])
            except ValueError as e:
                parse_errors.append(str(e))
                continue

            denom = compton_peak + photoelec_peak + pairprod_peak
            if denom == 0:
                parse_errors.append(f"{job_name}: mu(E0) bang 0 ca 3 loai, khong the tinh R")
                continue

            r_value = compton_peak / denom
            result.loc[idx, mat] = r_value

    result.to_excel(result_path, index=False)
    print(f"Da luu ket qua he so R vao '{result_path}'")

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
    outputs_dir = sys.argv[2] if len(sys.argv) > 2 else "outputs"
    result_path = sys.argv[3] if len(sys.argv) > 3 else "R_results.xlsx"
    main(excel_path, outputs_dir, result_path)
