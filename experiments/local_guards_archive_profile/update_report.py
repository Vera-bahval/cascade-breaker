"""Render the current completion report.

The historical replacement-based generator remains at commit
82d8ad24b344d612537fdf3f5490f82005645878; reproduce that report from that checkout.
This entry point never rewrites or rehashes historical manifests.
"""
from experiments.local_guards_completion.render import run


if __name__ == '__main__':
    run()
