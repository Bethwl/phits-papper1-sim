"""
Chay hang loat cac job PHITS - CHAY SONG SONG, moi job trong 1 thu muc rieng
(tranh xung dot file tam khi nhieu tien trinh PHITS chay chung 1 thu muc).

Cau truc mong doi (sinh boi generate_inputs.py):
    inputs/s1_60keV/s1_60keV.inp
    inputs/s1_80keV/s1_80keV.inp
    ...

Moi job hien sinh ra 3 file output (3 tally T-Interact trong vung mau):
    interact_compton_{stem}.out    - pho tuong tac Compton
    interact_photoelec_{stem}.out  - pho tuong tac quang dien
    interact_pairprod_{stem}.out   - pho tuong tac tao cap
    (dung de tinh R = mu_compton / (mu_compton + mu_photoelec + mu_pairprod))

Chay: python3 run_batch.py inputs/ outputs/ [lenh_phits] [so_luong_song_song] [timeout_giay] [file_danh_sach_job]
Vi du: python3 run_batch.py inputs/ outputs/ phits.sh 30
       python3 run_batch.py inputs/ outputs/ phits.sh 3 7200 failed_jobs.txt

GHI CHU: job nang luong cao (vai MeV tro len, bat negs=1) mo phong EM shower
(bremsstrahlung, tao cap, huy cap) nen ton nhieu thoi gian hon han job nang
luong thap - khong phai loi PHITS. Neu thay nhieu job timeout dong loat o
vung nang luong cao, hay GIAM workers (vd 3-6 thay vi 30) de moi job duoc
nhieu CPU hon (do dang chia 1 core cho qua nhieu tien trinh cung luc), va
TANG timeout (vd 3600-7200s) cho cac job nay co du thoi gian chay xong.
"""
import sys
import subprocess
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_one(job_dir: Path, phits_cmd: str, outputs_dir: Path, timeout: int):
    """Chay 1 job (1 thu muc rieng), tra ve (ten_job, thanh_cong, thong_bao_loi)."""
    # QUAN TRONG: khong dung glob("*.inp") lay bua file dau tien - khi bat
    # negs=1, PHITS tu sinh file phu tro "pegs5.inp" (du lieu tiet dien
    # electron) ngay trong thu muc job, nen thu muc co the co 2 file .inp.
    # Phai chi dinh dung ten file khop voi ten thu muc job (dung quy uoc cua
    # generate_inputs.py: {job_name}/{job_name}.inp), tranh chay nham
    # pegs5.inp (khong phai input hop le -> PHITS crash, khong sinh output).
    inp_file = job_dir / f"{job_dir.name}.inp"
    if not inp_file.exists():
        return job_dir.name, False, f"khong tim thay {inp_file.name} trong thu muc job"

    # Moi job hien co 3 file output tuong ung 3 tally T-Interact trong .inp
    # (compton, photoelec, pairprod), dung de tinh he so R = mu_compton /
    # (mu_compton + mu_photoelec + mu_pairprod)
    expected_outs = [
        f"interact_compton_{inp_file.stem}.out",
        f"interact_photoelec_{inp_file.stem}.out",
        f"interact_pairprod_{inp_file.stem}.out",
    ]

    try:
        result = subprocess.run(
            [phits_cmd, inp_file.name],
            cwd=str(job_dir),                 # chay ngay trong thu muc rieng cua job nay
            capture_output=True, text=True, timeout=timeout,
        )

        missing_files = [f for f in expected_outs if not (job_dir / f).exists()]
        if result.returncode != 0 or missing_files:
            tail = (result.stderr or result.stdout)[-300:]
            if missing_files:
                tail = f"thieu file: {missing_files} | " + tail
            return job_dir.name, False, tail

        # Copy vao outputs_dir/{job_name}/ (giu nguyen 1-thu-muc-1-job) de khop
        # dung cau truc ma parse_results.py dang tim: outputs/{job}/interact_*_{job}.out
        job_out_dir = outputs_dir / job_dir.name
        job_out_dir.mkdir(parents=True, exist_ok=True)
        for f in expected_outs:
            shutil.copy(str(job_dir / f), str(job_out_dir / f))

        return job_dir.name, True, ""
    except Exception as e:
        return job_dir.name, False, str(e)


def main(inputs_dir: str, outputs_dir: str, phits_cmd: str = "phits.sh",
         workers: int = 30, timeout: int = 600, job_list_file: str = None):
    inputs_dir = Path(inputs_dir)
    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    job_dirs = sorted(d for d in inputs_dir.iterdir() if d.is_dir())

    if job_list_file:
        wanted = {line.strip() for line in Path(job_list_file).read_text().splitlines() if line.strip()}
        job_dirs = [d for d in job_dirs if d.name in wanted]
        not_found = wanted - {d.name for d in job_dirs}
        if not_found:
            print(f"CANH BAO: {len(not_found)} ten job trong '{job_list_file}' khong khop thu muc nao trong '{inputs_dir}':")
            for n in sorted(not_found):
                print(" -", n)

    print(f"Tim thay {len(job_dirs)} job -> chay song song {workers} tien trinh, timeout {timeout}s/job")

    done, failed = 0, []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(run_one, d, phits_cmd, outputs_dir, timeout): d for d in job_dirs}
        for fut in as_completed(futures):
            name, ok, err = fut.result()
            done += 1
            status = "OK" if ok else f"LOI: {err}"
            print(f"[{done}/{len(job_dirs)}] {name} -> {status}")
            if not ok:
                failed.append(name)

    print(f"\nHoan tat. {len(job_dirs) - len(failed)}/{len(job_dirs)} thanh cong.")
    if failed:
        print("Cac job bi loi (co the chay lai rieng cac job nay):")
        for f in failed:
            print(" -", f)
        # Ghi san file danh sach job loi de chay lai lan sau, khong can go tay
        Path("failed_jobs.txt").write_text("\n".join(failed) + "\n")
        print("\n(Da ghi danh sach job loi vao 'failed_jobs.txt' - dung file nay lam tham so thu 6 de chay lai)")


if __name__ == "__main__":
    inputs_dir = sys.argv[1] if len(sys.argv) > 1 else "inputs"
    outputs_dir = sys.argv[2] if len(sys.argv) > 2 else "outputs"
    phits_cmd = sys.argv[3] if len(sys.argv) > 3 else "phits.sh"
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    timeout = int(sys.argv[5]) if len(sys.argv) > 5 else 600
    job_list_file = sys.argv[6] if len(sys.argv) > 6 else None
    main(inputs_dir, outputs_dir, phits_cmd, workers, timeout, job_list_file)
