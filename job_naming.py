"""
job_naming.py - Chuan hoa quy uoc dat ten file 1-to-1 Flat Pool
Quy tac: Luu tat ca file raw vao 1 pool chung duy nhat (02_Flux_Data),
khong chia theo may/runner/account.
Dinh dang truc quan: {sample}_{thickness}cm_{energy}keV.csv (Vi du: S1_5cm_50keV.csv)
"""

def format_job_name(sample: str, thickness_cm: float, energy_mev: float) -> str:
    """
    Tao ten file chuan theo mau: {sample}_{thickness}cm_{energy}keV
    Vi du:
      format_job_name('S1', 5.0, 0.05)   -> 'S1_5cm_50keV'
      format_job_name('S7', 0.1, 0.015)  -> 'S7_0.1cm_15keV'
      format_job_name('BLANK', 0.5, 1.0) -> 'BLANK_0.5cm_1000keV'
    """
    s = str(sample).upper().strip()
    th = float(thickness_cm)
    th_str = f"{th:g}cm"

    e = float(energy_mev)
    e_kev = round(e * 1000.0, 4)
    if e_kev == int(e_kev):
        e_str = f"{int(e_kev)}keV"
    else:
        e_str = f"{e_kev:g}keV"

    return f"{s}_{th_str}_{e_str}"

def get_candidate_filenames(sample: str, thickness_cm: float, energy_mev: float) -> list:
    """
    Tra ve tat ca cac bien the ten file (bao gom ten chuan moi va ten legacy cu)
    de checklist_verifier co the nhan dien chinh xac trong pool chung.
    """
    s = str(sample).upper().strip()
    th = float(thickness_cm)
    e = float(energy_mev)
    e_kev = round(e * 1000.0, 4)
    e_kev_int = int(round(e_kev))

    candidates = [
        # 1. Ten chuan moi: S1_5cm_50keV.csv
        f"{s}_{th:g}cm_{e_kev:g}keV.csv",
        f"{s}_{th:g}cm_{e_kev_int}keV.csv",
        # 2. Truong hop MeV: S1_5cm_1MeV.csv
        f"{s}_{th:g}cm_{e:g}MeV.csv",
        # 3. Legacy numeric: S1_0.050_5.000.csv
        f"{s}_{e:.3f}_{th:.3f}.csv",
        # 4. Legacy macro lowercase: s1_50kev_th5cm.csv
        f"{s.lower()}_{e_kev_int}kev_th{th:g}cm.csv",
        f"{s.lower()}_{e_kev_int}kev_th{th:.1f}cm.csv"
    ]
    # Loai bo cac ten trung lap, giu thu tu uu tien
    seen = set()
    result = []
    for c in candidates:
        c_lower = c.lower()
        if c_lower not in seen:
            seen.add(c_lower)
            result.append(c)
    return result
