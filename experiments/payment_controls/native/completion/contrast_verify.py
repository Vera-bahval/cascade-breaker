"""Recompute the sealed Jev contrast without writing over its saved score."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch

from . import contrast_run


def main():
    capture = StringIO()
    sealed_score = contrast_run.PRIVATE / "score.json"
    published = Path(__file__).with_name("contrast_results.json")

    def compare_saved(path, output):
        if path != sealed_score or contrast_run.read(path) != json.loads(json.dumps(output)):
            raise SystemExit("The recomputed result differs from the sealed result.")

    with patch.object(contrast_run, "save", compare_saved), redirect_stdout(capture):
        contrast_run.score()
    if contrast_run.read(published) != json.loads(capture.getvalue()):
        raise SystemExit("The recomputed result differs from the published result.")
    print("Verified sealed and published scores from the frozen inputs and 144 retained receipts.")


if __name__ == "__main__":
    main()
