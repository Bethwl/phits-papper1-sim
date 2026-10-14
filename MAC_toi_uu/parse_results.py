"""
Doc flux tu file .out cua PHITS (tally T-Cross, dinh dang ANGEL), gom lai theo
dung layout Energy x s1..s6, xuat ra file Excel.

Cau truc thu muc (khop voi generate_inputs.py): moi job PHITS chay trong
MOT thu muc rieng, vi du:
    outputs/s1_15000keV/cross_spectrum_s1_15000keV.out
    outputs/blank_15000keV/cross_spectrum_blank_15000keV.out

Moi job chi doc 1 file:
  - cross_spectrum_{job}.out : pho toan phan (log, e-type=3), axis=eng.

CHI LAY 1 SO DUY NHAT cho moi job: gia tri "photon" (flux) o BIN NANG LUONG
CAO NHAT (dong du lieu CUOI CUNG trong bang, ngay truoc dong "# sum over").
Day la bin sat dinh nang luong nguon nhat -> dai dien flux uncollided/dinh.

Vi du thuc te (cross_spectrum_s1_15000keV.out, dinh dang PHITS 3.36):
    #  e-lower      e-upper        photon    r.err
       ...
       1.4973E+01   1.6500E+01   5.0929E+00   0.0000
    -> lay so 5.0929E+00 (cot photon cua dong cuoi cung).

Chay: python parse_results.py thickness_table.xlsx outputs/ flux_results.xlsx
"""
import sys
import pandas as pd
from pathlib import Path


def parse_peak_bin(filepath: Path) -> float:
    """
    Doc file pho T-Cross (axis=eng, e-type=3), tra ve gia tri flux (cot
    'photon') cua bin nang luong CAO NHAT co du lieu (khac 0).

    LUU Y QUAN TRONG: KHONG duoc lay mu mu dong du lieu cuoi cung trong
    bang, vi bin tren cung (sat emax) nhieu khi bang 0 -- do bien bin
    (e-lower/e-upper) khong khop chinh xac voi e0, nen dinh flux uncollided
    thuc te lai roi vao bin ngay ben duoi. Vi du thuc te:
        ...
        3.2592E-02   3.3784E-02   7.0193E-01   0.0025   <- dinh flux thuc su
        ...
        1.4973E+01   1.6500E+01   0.0000E+00   0.0000   <- dong cuoi bang = 0

    Cach xu ly: QUET TU DUOI LEN (tu bin nang luong cao nhat giam dan), gap
    dong DAU TIEN co gia tri khac 0 thi lay dong do -- do chinh la bin sat
    dinh nguon nhat co du lieu thuc.

    Dinh dang ANGEL thuc te:
        #  e-lower      e-upper        photon    r.err
           1.0000E-03   1.1020E-03   0.0000E+00  0.0000
           ...
    """
    lines = filepath.read_text().splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and "e-lower" in stripped.lower() and "photon" in stripped.lower():
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

    # Quet TU DUOI LEN (bin nang luong cao nhat -> thap dan), lay dong
    # DAU TIEN co flux khac 0. Cot ap chot la r.err, cot truoc do la photon.
    for row in reversed(data_rows):
        flux = row[-2]
        if flux != 0:
            return flux

    # Toan bo pho bang 0 (truong hop hiem, vi du khong co photon nao toi)
    return 0.0


def main(excel_path: str, outputs_dir: str, result_path: str):
    df = pd.read_excel(excel_path)
    materials = [c for c in df.columns if c.lower() != "energy"]
    outputs_dir = Path(outputs_dir)

    result = df[["Energy"]].copy()
    columns = ["blank"] + materials
    for col in columns:
        result[col] = None

    missing = []
    parse_errors = []

    for idx, row in df.iterrows():
        energy_kev = int(round(row["Energy"]))

        for col in columns:
            # job_name phai khop CHINH XAC voi thu muc ma generate_inputs.py da tao:
            #   blank -> inputs/blank_{energy}keV/...
            #   vat lieu -> inputs/{mat}_{energy}keV/...
            job_name = f"blank_{energy_kev}keV" if col == "blank" else f"{col}_{energy_kev}keV"
            job_dir = outputs_dir / job_name

            cross_name = f"cross_spectrum_{job_name}.out"
            cross_path = job_dir / cross_name

            if not cross_path.exists():
                missing.append(str(cross_path))
                continue

            try:
                peak_flux = parse_peak_bin(cross_path)
            except ValueError as e:
                parse_errors.append(str(e))
                continue

            result.loc[idx, col] = peak_flux

    result.to_excel(result_path, index=False)
    print(f"Da luu ket qua vao '{result_path}'")

    if missing:
        print(f"\nCANH BAO: {len(missing)} file khong tim thay (bo qua):")
        for m in missing[:20]:
            print(" -", m)

    if parse_errors:
        print(f"\nCANH BAO: {len(parse_errors)} loi khi doc du lieu:")
        for e in parse_errors[:20]:
            print(" -", e)


if __name__ == "__main__":
    excel_path = sys.argv[1] if len(sys.argv) > 1 else "thickness_table.xlsx"
    outputs_dir = sys.argv[2] if len(sys.argv) > 2 else "outputs"
    result_path = sys.argv[3] if len(sys.argv) > 3 else "flux_results.xlsx"
    main(excel_path, outputs_dir, result_path)
