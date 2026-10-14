"""
run_phits_papper1.py - Parallel worker for PHITS Simulation (2026_7_5_phits_papper1)
Supports 5 sub-projects:
1. Alpha
2. MAC_co_dinh
3. MAC_toi_uu
4. Proton
5. R
Runs on GitHub Actions Swarm (13 active accounts x 10 runners = 130 runners).
Uploads raw 1-to-1 CSV results directly to Flat Common Pool (02_Flux_Data).
Uploads runner simulation outputs (.out files) to 03_Simulation_Outputs.
Uploads execution log and benchmark timing to 05_Execution_Logs_and_Benchmarks.
"""

import os
import sys
import time
import json
import shutil
import zipfile
import argparse
import subprocess
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import gdrive_helper
import job_naming

DEFAULT_PROJECT_FOLDER_ID = "1tt3-uokplpyFiQ6xgU5YmlDQ_9ihHlUl"


def parse_args():
    parser = argparse.ArgumentParser(description="PHITS Parallel Worker for 2026_7_5_phits_papper1")
    parser.add_argument("--runner-id", type=int, required=True, help="ID runner (1..10)")
    parser.add_argument("--num-runners", type=int, default=10, help="Tong so runner tren account nay")
    parser.add_argument("--gdrive-folder", type=str, default=DEFAULT_PROJECT_FOLDER_ID)
    parser.add_argument("--plan-file", type=str, default="phits_papper1_plan_14acc.json")
    parser.add_argument("--github-user", type=str, default=None)
    parser.add_argument("--package-path", type=str, default="phits_pack/phits_package.tar.gz")
    parser.add_argument("--omp", type=int, default=2)
    parser.add_argument("--timeout-hours", type=float, default=2.5)
    return parser.parse_args()


def setup_phits_environment(tar_path: Path, target_dir: Path) -> tuple:
    target_dir.mkdir(parents=True, exist_ok=True)
    phits_bin = None
    matches = list(target_dir.rglob("phits"))
    for m in matches:
        if m.is_file():
            phits_bin = m
            break

    if not phits_bin or not phits_bin.exists():
        print(f">>> [SETUP] Dang giai nen goi PHITS tu {tar_path} vao {target_dir}...")
        subprocess.run(["tar", "-zxf", str(tar_path), "-C", str(target_dir)], check=True)
        matches = list(target_dir.rglob("phits"))
        for m in matches:
            if m.is_file():
                phits_bin = m
                break

    if not phits_bin:
        raise FileNotFoundError(f"Khong tim thay binary 'phits' sau khi giai nen {tar_path}")

    subprocess.run(["chmod", "+x", str(phits_bin)], check=True)
    phits_root = phits_bin.parent

    # Giai nen bo sung EGS neu co
    egs_tar = tar_path.parent / "egs.tar.gz"
    if egs_tar.exists() and not (phits_root / "XS" / "egs").exists():
        print(f">>> [SETUP] Dang giai nen goi EGS tu {egs_tar} vao {phits_root / 'XS'}...")
        (phits_root / "XS").mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar", "-zxf", str(egs_tar), "-C", str(phits_root / "XS")], check=True)
        print(f">>> [SETUP] EGS data san sang tai: {phits_root / 'XS' / 'egs'}")

    print(f">>> [SETUP] PHITS binary san sang tai: {phits_bin} (root: {phits_root})")
    return phits_bin, phits_root


def parse_peak_bin(filepath: Path) -> float:
    """Doc file pho T-Cross de lay flux o bin gan dinh nhat."""
    lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and "e-lower" in stripped.lower() and "photon" in stripped.lower():
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Khong tim thay header pho trong {filepath.name}")

    data_rows = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            if data_rows:
                break
            continue
        if stripped.startswith("#"):
            continue
        parts = stripped.split()
        try:
            nums = [float(p) for p in parts]
            if len(nums) >= 2:
                data_rows.append(nums)
        except ValueError:
            continue

    if not data_rows:
        return 0.0

    for row in reversed(data_rows):
        flux = row[-2]
        if flux != 0:
            return flux
    return 0.0


def extract_scalar_from_tally(filepath: Path) -> float:
    """Doc flux/dose scalar tu file tally."""
    lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            parts = stripped.split()
            try:
                nums = [float(p) for p in parts]
                if nums:
                    return nums[-2] if len(nums) >= 2 else nums[0]
            except ValueError:
                pass
    return 0.0


def main():
    args = parse_args()
    acc_name = args.github_user or os.environ.get("GITHUB_REPOSITORY_OWNER") or "runner"

    print("=" * 80)
    print(f"🚀 STARTING PHITS RUNNER #{args.runner_id} (Account: {acc_name})")
    print(f"Project: 2026_7_5_phits_papper1 | Plan file: {args.plan_file}")
    print(f"Google Drive Project ID: {args.gdrive_folder}")
    print("=" * 80)

    # 1. Connect Google Drive and find folders
    drive_service = None
    subfolders = {}
    existing_drive_files = set()
    try:
        drive_service = gdrive_helper.get_drive_service()
        subfolders = gdrive_helper.get_or_create_subfolders(drive_service, parent_id=args.gdrive_folder)
        print(">>> [DRIVE] Ket noi Google Drive thanh cong!")
        for k, v in subfolders.items():
            print(f"  • {k}: {v}")

        # Scan 02_Flux_Data for Auto-Resume
        flux_id = subfolders.get("02_Flux_Data")
        if flux_id:
            page_token = None
            while True:
                q = f"'{flux_id}' in parents and trashed = false"
                res = drive_service.files().list(
                    q=q, supportsAllDrives=True, includeItemsFromAllDrives=True,
                    fields="nextPageToken, files(name)", pageSize=1000, pageToken=page_token
                ).execute()
                for item in res.get("files", []):
                    existing_drive_files.add(item["name"].lower().strip())
                page_token = res.get("nextPageToken")
                if not page_token:
                    break
            print(f">>> [RESUME] Tim thay {len(existing_drive_files)} file da co tren 02_Flux_Data.")
    except Exception as e:
        print(f">>> [CANH BAO] Loi ket noi Google Drive: {e}. Tiep tuc luu local.")

    # 2. Setup PHITS binary
    work_dir = Path("/tmp/phits_work") if os.name != "nt" else Path(r"C:\tmp\phits_work")
    work_dir.mkdir(parents=True, exist_ok=True)
    phits_bin, phits_root = setup_phits_environment(Path(args.package_path), work_dir / "phits_dist")

    # 3. Load plan file
    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        raise FileNotFoundError(f"Khong tim thay file plan: {plan_path}")

    with open(plan_path, "r", encoding="utf-8") as f:
        full_plan = json.load(f)

    my_account_plan = full_plan.get(acc_name, {})
    my_jobs = my_account_plan.get(str(args.runner_id), [])

    if not my_jobs:
        # Fallback: neu account name khong co trong plan, lay round-robin theo runner_id
        all_jobs_flat = []
        for acc_k, r_dict in full_plan.items():
            for r_k, j_list in r_dict.items():
                all_jobs_flat.extend(j_list)
        my_jobs = [j for i, j in enumerate(all_jobs_flat) if i % args.num_runners == (args.runner_id - 1)]

    print(f">>> [PLAN] Runner #{args.runner_id} duoc giao {len(my_jobs)} jobs.")

    # 4. Filter jobs already completed on Drive (Auto-Resume)
    todo_jobs = []
    for j in my_jobs:
        target_csv_name = f"{j['job_name'].lower()}.csv"
        if target_csv_name in existing_drive_files:
            continue
        todo_jobs.append(j)

    print(f">>> [AUTO-RESUME] Con lai: {len(todo_jobs)} / {len(my_jobs)} jobs can chay.")

    if not todo_jobs:
        print(f"🎉 Toan bo {len(my_jobs)} jobs cua Runner #{args.runner_id} da hoan tat 100%! Thoat som.")
        return

    # 5. Run simulation loop
    start_total = time.time()
    outputs_to_zip = []
    benchmark_lines = []

    for idx, job in enumerate(todo_jobs, 1):
        elapsed_overall = time.time() - start_total
        if elapsed_overall > (args.timeout_hours * 3600 - 600):
            print(f">>> [TIMEOUT SAFEGUARD] Sap vuot qua {args.timeout_hours}h. Thoat de dong bo an toan.")
            break

        jname = job["job_name"]
        sp = job["sub_project"]
        rel_path = job["rel_path"]
        inp_file = Path(rel_path)

        if not inp_file.exists():
            print(f">>> [LOI] Khong tim thay file input: {inp_file}")
            continue

        job_dir = inp_file.parent
        print(f"\n[{idx}/{len(todo_jobs)}] Chay job: {jname} ({sp}) tai {job_dir}...")
        t0 = time.time()

        env = os.environ.copy()
        env["PHITSPATH"] = str(phits_root)
        env["OMP_NUM_THREADS"] = str(args.omp)

        # Chay PHITS bang lenh stdin: phits < input.inp
        cmd = f'"{phits_bin}" < "{inp_file.name}"'
        res = subprocess.run(cmd, shell=True, cwd=str(job_dir), env=env, capture_output=True, text=True)
        job_elapsed = time.time() - t0

        # Kiem tra file out sinh ra
        out_files = list(job_dir.glob("*.out"))
        if not out_files or res.returncode != 0:
            tail_msg = (res.stderr or res.stdout)[-300:]
            print(f"    ❌ LOI CHAY PHITS (code {res.returncode}): {tail_msg}")
            continue

        print(f"    ✅ Hoan thanh ({job_elapsed:.1f}s) | Sinh {len(out_files)} files .out")

        # Trich xuat so lieu theo tung sub-project
        extracted_metric = 0.0
        try:
            if sp in ["MAC_co_dinh", "MAC_toi_uu"]:
                cross_outs = list(job_dir.glob("cross_spectrum_*.out"))
                if cross_outs:
                    extracted_metric = parse_peak_bin(cross_outs[0])
            elif sp == "R":
                compton_outs = list(job_dir.glob("interact_compton_*.out"))
                if compton_outs:
                    extracted_metric = extract_scalar_from_tally(compton_outs[0])
            elif sp in ["Alpha", "Proton"]:
                range_outs = list(job_dir.glob("range_profile_*.out"))
                if range_outs:
                    extracted_metric = extract_scalar_from_tally(range_outs[0])
        except Exception as e:
            print(f"    ⚠️ Warning khi parse metric: {e}")

        # Ghi file 1-to-1 CSV: {job_name}.csv
        local_csv = work_dir / f"{jname}.csv"
        csv_df = pd.DataFrame([{
            "job_name": jname,
            "sub_project": sp,
            "inp_name": inp_file.name,
            "metric_value": extracted_metric,
            "elapsed_seconds": round(job_elapsed, 2),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }])
        csv_df.to_csv(local_csv, index=False)

        # Stream ngay lap tuc len Google Drive 02_Flux_Data
        if drive_service and "02_Flux_Data" in subfolders:
            try:
                gdrive_helper.upload_file_to_folder(drive_service, str(local_csv), subfolders["02_Flux_Data"])
                print(f"    ☁️ Streamed {local_csv.name} -> Google Drive (02_Flux_Data)")
            except Exception as e:
                print(f"    ⚠️ Upload CSV failed: {e}")

        for o in out_files:
            outputs_to_zip.append(o)

        benchmark_lines.append(f"{jname},{sp},{job_elapsed:.2f}")

    # 6. Upload runner outputs (.zip) vao 03_Simulation_Outputs
    if outputs_to_zip and drive_service and "03_Simulation_Outputs" in subfolders:
        runner_zip = work_dir / f"outputs_{acc_name}_runner{args.runner_id:02d}.zip"
        print(f"\n>>> Dang dong goi {len(outputs_to_zip)} file .out vao {runner_zip.name}...")
        with zipfile.ZipFile(runner_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for out_f in outputs_to_zip:
                zf.write(out_f, arcname=f"{out_f.parent.name}/{out_f.name}")
        try:
            gdrive_helper.upload_file_to_folder(drive_service, str(runner_zip), subfolders["03_Simulation_Outputs"])
            print(f">>> Da upload {runner_zip.name} len 03_Simulation_Outputs")
        except Exception as e:
            print(f"⚠️ Upload zip failed: {e}")

    # 7. Upload benchmark timing log vao 05_Execution_Logs_and_Benchmarks
    total_time = time.time() - start_total
    log_file = work_dir / f"benchmark_{acc_name}_runner{args.runner_id:02d}.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"Account: {acc_name} | Runner ID: {args.runner_id}\n")
        f.write(f"Total jobs executed: {len(benchmark_lines)}\n")
        f.write(f"Total time: {total_time:.2f}s\n")
        f.write("job_name,sub_project,elapsed_seconds\n")
        for line in benchmark_lines:
            f.write(line + "\n")

    if drive_service and "05_Execution_Logs_and_Benchmarks" in subfolders:
        try:
            gdrive_helper.upload_file_to_folder(drive_service, str(log_file), subfolders["05_Execution_Logs_and_Benchmarks"])
            print(f">>> Da upload log benchmark len 05_Execution_Logs_and_Benchmarks")
        except Exception as e:
            print(f"⚠️ Upload log failed: {e}")

    print("\n" + "=" * 80)
    print(f"🏁 RUNNER #{args.runner_id} HOAN TAT! Chay {len(benchmark_lines)} jobs trong {total_time:.1f}s.")
    print("=" * 80)


if __name__ == "__main__":
    main()
