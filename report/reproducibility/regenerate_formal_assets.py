#!/usr/bin/env python3
"""Regenerate report assets with black labels and bold black plot headings."""
import argparse
import importlib.util
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--benchmark-root', type=Path, required=True)
parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1])
args = parser.parse_args()
source = args.benchmark_root.resolve() / 'scripts' / 'make_research_assets.py'
spec = importlib.util.spec_from_file_location('research_assets', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.plt.rcParams.update({
    'axes.labelcolor': 'black',
    'axes.titlecolor': 'black',
    'axes.titleweight': 'bold',
    'text.color': 'black',
})
save_assets = module.save


def save_formal_figure(figure, output, name):
    for label in figure.findobj(match=module.matplotlib.text.Text):
        label.set_color('black')
    save_assets(figure, output, name)


module.save = save_formal_figure
sys.argv = [str(source), '--out', str(args.out.resolve())]
module.main()
