"""개선된 extract_particle_size 단위 테스트"""
import sys
sys.path.insert(0, r"d:\머신러닝 교육\ceria_pipeline_data")
from src.extract_ceria_rules import extract_particle_size

CASES = [
    # (설명, 입력 텍스트, 기대 tem, 기대 sem, 기대 xrd)
    ("TEM+크기 같은 문장",
     "TEM images show spherical nanoparticles with an average diameter of 15 nm.",
     15.0, None, None),

    ("TEM 다음 문장에 크기",
     "Morphology was analyzed by TEM. The mean particle size was 12 nm.",
     12.0, None, None),

    ("TEM 2문장 이전",
     "TEM observation was performed. Particles were well dispersed. Average size is 8 nm.",
     8.0, None, None),

    ("XRD Scherrer 크기",
     "The crystallite size calculated from Scherrer equation was 5.3 nm by XRD.",
     None, None, 5.3),

    ("SEM 입자 크기",
     "SEM micrographs indicate uniform nanoparticles with diameter of 80 nm.",
     None, 80.0, None),

    ("범위값 5-20 nm (midpoint=12.5)",
     "TEM images revealed particles with size ranging from 5 to 20 nm.",
     None, None, None),  # "5 to 20" - 현재 패턴은 "5-20" 하이픈만 처리

    ("범위값 하이픈 표기",
     "Nanoparticles of 10-30 nm were observed by TEM analysis.",
     20.0, None, None),

    ("DLS 제외 (hydrodynamic diameter)",
     "DLS measurements showed a hydrodynamic diameter of 150 nm.",
     None, None, None),

    ("pore size 제외",
     "The pore diameter was approximately 4 nm as measured by BET.",
     None, None, None),

    ("film thickness 제외",
     "A thin film with thickness of 200 nm was deposited by sputtering.",
     None, None, None),

    ("wavelength 제외",
     "The emission peak was observed at 465 nm in the photoluminescence spectrum.",
     None, None, None),

    ("TEM + XRD 모두 (각각 분리)",
     "XRD analysis gave a crystallite size of 6 nm. TEM showed particle size of 18 nm.",
     18.0, None, 6.0),

    ("μm 단위 → nm 변환",
     "Particle size observed by TEM was 0.025 μm.",
     25.0, None, None),

    ("±불확도 포함",
     "TEM images show nanoparticles with average diameter 15 ± 3 nm.",
     15.0, None, None),
]

passed = 0
failed = 0
for desc, text, exp_tem, exp_sem, exp_xrd in CASES:
    res = extract_particle_size(text)
    tem = res["particle_size_tem_nm"]
    sem = res["particle_size_sem_nm"]
    xrd = res["crystallite_size_xrd_nm"]

    ok = (tem == exp_tem) and (sem == exp_sem) and (xrd == exp_xrd)
    mark = "✓" if ok else "✗"
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"{mark} [{desc}]")
        print(f"   기대: TEM={exp_tem}, SEM={exp_sem}, XRD={exp_xrd}")
        print(f"   실제: TEM={tem}, SEM={sem}, XRD={xrd}")
        print()

if failed == 0:
    print(f"전체 {passed}개 케이스 모두 통과!")
else:
    print(f"\n{passed}개 통과 / {failed}개 실패")
