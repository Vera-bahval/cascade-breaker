"""Standalone scientific figure from existing scored artifacts; no inference."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def metric(path, method, policy, scope, value):
    return next(r for r in json.loads(path.read_text())['aggregates']
                if (r['method'],r['policy_oracle'],r['slice'],r['value']) == (method,policy,scope,value))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('refusing overwrite')
    args.output.mkdir(parents=True)
    archive = HERE / 'results/archive-evaluation/metrics.json'
    closed = HERE / 'results/closed-evaluation/metrics.json'
    fig, axes = plt.subplots(1,2,figsize=(10.6,4.5),constrained_layout=True)
    for ax in axes:
        ax.set_xlim(-4,106); ax.set_ylim(-5,107)
        ax.set_xticks([0,25,50,75,100]); ax.set_yticks([0,25,50,75,100])
        ax.grid(alpha=.2); ax.set_axisbelow(True)
    for method,label,color,offset in [
        ('control_p4_v3','P4 v3','#2366a0',(7,7)),
        ('A_with_P4','A / A+B: нет proof сессии','#c14c32',(-205,-17))]:
        r=metric(archive,method,'A','cohort','original_main')
        x,y=r['source_legit_interruption_rate_whole']*100,r['harm_prevention_rate']*100
        axes[0].scatter(x,y,s=70,color=color)
        axes[0].annotate(label,(x,y),xytext=offset,textcoords='offset points',fontsize=9)
    axes[0].set_title('Архив: исходные 1 352 эпизода')
    axes[0].set_xlabel('Прерванные исходно честные задачи, %')
    axes[0].set_ylabel('Архивный вред, который остановился бы, %')
    for method,label,color,offset in [
        ('control_p4_v3','P4 v3','#2366a0',(8,-12)),
        ('A_with_P4','A','#cf9632',(8,-12)),
        ('A_plus_allB','A+B','#2a835e',(8,-12))]:
        r=metric(closed,method,'A+B','all',None)
        x,y=r['safe_stop_fpr'],r['intervention_recall']
        if x is None or y is None:
            continue
        axes[1].scatter(x*100,y*100,s=70,color=color)
        axes[1].annotate(label,(x*100,y*100),xytext=offset,textcoords='offset points',fontsize=9)
    axes[1].set_title('400 новых синтетических состояний')
    axes[1].set_xlabel('Остановлены допустимые по A+B состояния, %')
    axes[1].set_ylabel('Остановлены известные нарушения A+B, %')
    axes[1].text(.98,.07,'Не показаны 106 gold UNKNOWN.\nA+B разрешил 2 из них.',
                 transform=axes[1].transAxes,ha='right',fontsize=9)
    fig.suptitle('Разные популяции и разметка: эти панели нельзя подменять друг другом',fontsize=11)
    fig.savefig(args.output/'tradeoffs.svg')
    fig.savefig(args.output/'tradeoffs.png',dpi=170)
    plt.close(fig)


if __name__ == '__main__':
    main()
