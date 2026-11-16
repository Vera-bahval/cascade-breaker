import os
from concurrent.futures import ThreadPoolExecutor
from .batch import run_one

if __name__=="__main__":
    jobs=[(c,a,f) for c in ("chat-transfer","onboarding-transfer") for a in ("off","late-hybrid") for f in ("authorized","withheld")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_one,jobs))
