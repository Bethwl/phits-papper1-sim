"""
Chay hang loat cac job PHITS - CHAY SONG SONG, moi job trong 1 thu muc rieng
(tranh xung dot file tam khi nhieu tien trinh PHITS chay chung 1 thu muc).

Cau truc mong doi (sinh boi generate_inputs.py):
    inputs/s1_60keV/s1_60keV.inp
    inputs/s1_80keV/s1_80keV.inp
    ...

Moi job hien sinh ra 1 file output (1 tally T-Cross):
    cross_spectrum_{stem}.out   - pho toan phan (log), dung de lay flux o
                                  bin nang luong cao nhat (dinh nguon)

Chay: python3 run_batch.py inputs/ outputs/ [lenh_phits] [so_luong_song_song]
Vi du: python3 run_batch.py inputs/ outputs/ phits.sh 30
"""
import sys
import subprocess
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_one(job_dir: Path, phits_cmd: str, outputs_dir: Path):
    """Chay 1 job (1 thu muc rieng), tra ve (ten_job, thanh_cong, thong_bao_loi)."""
    inp_files = list(job_dir.glob("*.inp"))
    if not inp_files:
        return job_dir.name, False, "khong tim thay file .inp trong thu muc job"
    inp_file = inp_files[0]

    # Moi job hien chi con 1 file output tuong ung tally T-Cross duy nhat trong .inp
    expected_outs = [
        f"cross_spectrum_{inp_file.stem}.out",
    ]

    try:
        result = subprocess.run(
            [phits_cmd, inp_file.name],
            cwd=str(job_dir),                 # chay ngay trong thu muc rieng cua job nay
            capture_output=True, text=True, timeout=600,
        )

        missing_files = [f for f in expected_outs if not (job_dir / f).exists()]
        if result.returncode != 0 or missing_files:
            tail = (result.stderr or result.stdout)[-300:]
            if missing_files:
                tail = f"thieu file: {missing_files} | " + tail
            return job_dir.name, False, tail

        # Copy vao outputs_dir/{job_name}/ (giu nguyen 1-thu-muc-1-job) de khop
        # dung cau truc ma parse_results.py dang tim: outputs/{job}/cross_spectrum_{job}.out
        job_out_dir = outputs_dir / job_dir.name
        job_out_dir.mkdir(parents=True, exist_ok=True)
        for f in expected_outs:
            shutil.copy(str(job_dir / f), str(job_out_dir / f))

        return job_dir.name, True, ""
    except Exception as e:
        return job_dir.name, False, str(e)


def main(inputs_dir: str, outputs_dir: str, phits_cmd: str = "phits.sh", workers: int = 30):
    inputs_dir = Path(inputs_dir)
    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    job_dirs = sorted(d for d in inputs_dir.iterdir() if d.is_dir())
    print(f"Tim thay {len(job_dirs)} job -> chay song song {workers} tien trinh cung luc")

    done, failed = 0, []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(run_one, d, phits_cmd, outputs_dir): d for d in job_dirs}
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


if __name__ == "__main__":
    inputs_dir = sys.argv[1] if len(sys.argv) > 1 else "inputs"
    outputs_dir = sys.argv[2] if len(sys.argv) > 2 else "outputs"
    phits_cmd = sys.argv[3] if len(sys.argv) > 3 else "phits.sh"
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    main(inputs_dir, outputs_dir, phits_cmd, workers)
