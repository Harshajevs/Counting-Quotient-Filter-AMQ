#!/usr/bin/env python3
"""Generate the report's figures, tables and numeric macros from measured CSVs."""
import argparse
import json
import math
import re
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/'results/extended'
REPORT=ROOT/'results/report'
ORDER=['cqf','cuckoo','bloom','counting_bloom','blocked_bloom','xor','binary_fuse']
NAMES=dict(zip(ORDER,['CQF','Cuckoo','Bloom','Counting Bloom','Blocked Bloom','XOR','Fuse-style']))
COLORS=dict(zip(ORDER,['#147D83','#3F6691','#D28B36','#A05A71','#649B67','#7764A1','#537F83']))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,
 'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,
 'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#66727A',
 'axes.labelcolor':'#233D4D','text.color':'#233D4D','figure.facecolor':'white',
 'savefig.facecolor':'white','pdf.fonttype':42,'ps.fonttype':42})


def manifest(name):
    return dict(line.split('=',1) for line in (REPORT/name).read_text().splitlines() if '=' in line)


def raw(tag):
    base=pd.read_csv(EXT/f'paper_scale_{tag}_raw.csv')
    extra=pd.read_csv(EXT/f'additional_filters_{tag}_raw.csv')
    allrows=pd.concat([base,extra],ignore_index=True,sort=False)
    for dist in ['uniform','zipfian']:
        for name in ORDER:
            group=allrows[(allrows['filter']==name)&(allrows.distribution==dist)]
            if group.empty:raise ValueError(f'missing {tag} {name} {dist}')
    return allrows


def subset(df,name,dist):
    return df[(df['filter']==name)&(df.distribution==dist)]


def valid(group):
    return not ((group['filter']=='cuckoo').any() and (group.n_inserted<group.n_requested).any())


def stat(group,col,scale=1):
    if col.startswith('delete_') and (group['filter']=='bloom').any():
        return (float('nan'),float('nan'))
    if col not in group or not valid(group):return (float('nan'),float('nan'))
    x=pd.to_numeric(group[col],errors='coerce').dropna().to_numpy()/scale
    if not len(x):return (float('nan'),float('nan'))
    return float(x.mean()),float(x.std(ddof=1)) if len(x)>1 else 0.


def fnum(v,d=2):
    return f'{v:,.{d}f}' if math.isfinite(float(v)) else r'\na'


def rate(group,col,sd=True):
    a,b=stat(group,col,1e6)
    return f'{a:.2f} $\\pm$ {b:.2f}' if math.isfinite(a) and sd else fnum(a)


def mixed_query_rate(group,positive_fraction):
    """Sequential query-only model from mean batch costs, not a new timing."""
    if not valid(group):return float('nan')
    positive=pd.to_numeric(group.query_pos_time_s)/pd.to_numeric(group.n_requested)
    negative=pd.to_numeric(group.query_neg_time_s)/10_000_000
    return 1/(positive_fraction*positive.mean()+(1-positive_fraction)*negative.mean())


def wilson(rate,q=10_000_000):
    z=1.96;den=1+z*z/q
    c=(rate+z*z/(2*q))/den
    w=z/den*math.sqrt(rate*(1-rate)/q+z*z/(4*q*q))
    return max(0,c-w),min(1,c+w)


def sci(x):
    if not math.isfinite(float(x)):return r'\na'
    if x==0:return '0'
    exp=int(math.floor(math.log10(abs(x))))
    return f'${x/10**exp:.2f}\\times10^{{{exp}}}$'


def table(path,headers,rows,align=None):
    s='\\begin{tabular}{@{}'+(align or 'l'+'r'*(len(headers)-1))+'@{}}\n\\toprule\n'
    s+=' & '.join('\\textbf{'+h+'}' for h in headers)+r' \\'+'\n\\midrule\n'
    for row in rows:
        s+=' & '.join(map(str,row))+r' \\'+'\n'
    s+='\\bottomrule\n\\end{tabular}\n'
    path.write_text(s)


def save(fig,out,name):
    fig.savefig(out/'figures'/f'{name}.pdf',bbox_inches='tight',pad_inches=.05)
    fig.savefig(out/'figures'/f'{name}.png',dpi=170,bbox_inches='tight',pad_inches=.05)
    plt.close(fig)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    out=args.out.resolve()
    if not (REPORT/'COMPLETED.txt').exists():raise SystemExit('Complete and validate the report experiment matrix before generating assets.')
    for folder in ['figures','tables','data','reproducibility']:(out/folder).mkdir(parents=True,exist_ok=True)
    small,large=raw('report_1m'),raw('report_67m')
    control=pd.read_csv(EXT/'hash_modes_report_control_raw.csv')
    hashes=pd.read_csv(EXT/'hash_modes_report_67m_raw.csv')
    for df in [control,hashes]:df['mode']=df.config_param.str.extract(r'hash=(\w+)')
    geom=pd.read_csv(REPORT/'geometry_control_raw.csv');geom['q']=geom.config_param.str.extract(r'qbits=(\d+)').astype(int)
    compact=pd.read_csv(REPORT/'compact_zipf_raw.csv').iloc[0]
    msmall,mlarge=manifest('manifest_1m.txt'),manifest('manifest_67m.txt')
    macros={}
    def macro(k,v):macros[k]=str(v)
    def get(df,name,dist):return subset(df,name,dist)
    cqu,cqz=get(large,'cqf','uniform'),get(large,'cqf','zipfian')
    uniform_winner=max(ORDER,key=lambda f:stat(get(large,f,'uniform'),'query_pos_ops_sec')[0])
    macro('UniformFastestQuery',NAMES[uniform_winner])
    macro('UniformFastestQueryRate',f'{stat(get(large,uniform_winner,"uniform"),"query_pos_ops_sec",1e6)[0]:.2f}')
    for k,v in [('NumDistinctSmall',int(msmall['zipf_distinct_keys'])),('NumDistinctLarge',int(mlarge['zipf_distinct_keys'])),('MaxFrequencyLarge',int(mlarge['zipf_max_frequency']))]:macro(k,f'{v:,}')
    macro('CountingBloomInsertSkewLarge',f'{stat(get(large,"counting_bloom","zipfian"),"insert_ops_sec",1e6)[0]:.2f}')
    macro('GeometrySmallBits',f'{geom[geom.q==26].iloc[0].memory_bytes*8/63753420:.2f}')
    macro('GeometryLargeBits',f'{geom[geom.q==27].iloc[0].memory_bytes*8/63753420:.2f}')
    macro('PrimaryCqfMemory',f'{cqu.iloc[0].memory_bytes/1e6:.3f}')
    macro('CompactCbfMemoryRatio',f'{get(large,"counting_bloom","zipfian").iloc[0].memory_bytes/compact.memory_bytes:.1f}')
    macro('CountingBloomMemorySkew',f'{get(large,"counting_bloom","zipfian").iloc[0].memory_bytes/1e6:.3f}')
    macro('CompactMemory',f'{compact.memory_bytes/1e6:.3f}')
    macro('BloomMemoryLarge',f'{get(large,"bloom","uniform").iloc[0].memory_bytes/1e6:.3f}')
    macro('CompactFpr',sci(compact.measured_fp_rate))
    macro('CompactExpectedFpr',sci(int(mlarge['zipf_distinct_keys'])/2**28))
    for k,g,c in [('CqfInsertUniformLarge',cqu,'insert_ops_sec'),('CqfInsertSkewLarge',cqz,'insert_ops_sec'),('CqfPositiveUniformLarge',cqu,'query_pos_ops_sec'),('CqfNegativeUniformLarge',cqu,'query_neg_ops_sec')]:macro(k,f'{stat(g,c,1e6)[0]:.2f}')
    log=(REPORT/'run_67m.log').read_text()
    geometry=re.findall(r'geometry: slots=(\d+) occupied=(\d+) stored_fingerprints=(\d+) total_count=(\d+)',log)
    if len(geometry)!=6:raise ValueError(f'expected six CQF geometry log entries; found {len(geometry)}')
    macro('UniformOccupiedLarge',f'{int(geometry[0][1]):,}');macro('UniformStoredLarge',f'{int(geometry[0][2]):,}')
    macro('SkewOccupiedLarge',f'{int(geometry[3][1]):,}')
    def hgroup(df,mode,dist):return df[(df['mode']==mode)&(df.distribution==dist)]
    for dist,token in [('uniform','Uniform'),('zipfian','Skew')]:
        for col,op in [('insert_ops_sec','Insert'),('query_neg_ops_sec','Negative')]:
            default=stat(hgroup(hashes,'default',dist),col,1e6)[0]
            external=stat(hgroup(hashes,'none',dist),col,1e6)[0]
            macro('HashExternal'+op+token+'Ratio',f'{external/default:.3f}' if op=='Insert' else f'{external/default:.2f}')
            if dist=='uniform' and op=='Negative':
                macro('HashDefaultNegativeUniform',f'{default:.2f}');macro('HashExternalNegativeUniform',f'{external:.2f}')
    (out/'tables/numbers.tex').write_text('% Generated from measured CSVs.\n'+''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items()))
    table(out/'tables/workloads.tex',['Scale','Uniform $D$','Skewed $D$','Largest skewed count'],[
        ['1M',f'{int(msmall["uniform_distinct_keys"]):,}',f'{int(msmall["zipf_distinct_keys"]):,}',f'{int(msmall["zipf_max_frequency"]):,}'],
        ['67M',f'{int(mlarge["uniform_distinct_keys"]):,}',f'{int(mlarge["zipf_distinct_keys"]):,}',f'{int(mlarge["zipf_max_frequency"]):,}']])
    for dist,file in [('uniform','uniform_large'),('zipfian','zipf_large')]:
        rows=[]
        for name in ORDER:
            g=get(large,name,dist);first=g.iloc[0]
            vals=[rate(g,c) for c in ['insert_ops_sec','query_pos_ops_sec','query_neg_ops_sec','delete_ops_sec']]
            if not valid(g):vals=['Failed']*4
            rows.append([NAMES[name],*vals,f'{first.memory_bytes/1e6:.3f}'])
        table(out/'tables'/f'{file}.tex',['Filter','Insert','Positive','Negative','Delete','MB'],rows)
    rows=[]
    for dist in ['uniform','zipfian']:
        for name in ['xor','binary_fuse']:
            g=get(large,name,dist)
            prep=pd.to_numeric(g.preprocess_time_s);build=pd.to_numeric(g.build_time_s)
            rows.append([dist.title(),NAMES[name],f'{prep.mean():.3f}',f'{build.mean():.3f}',f'{stat(g,"build_ops_sec",1e6)[0]:.2f}',f'{(g.n_requested/(prep+build)).mean()/1e6:.2f}'])
    table(out/'tables/static_build.tex',['Input','Filter','Prep (s)','Build (s)','Build (M keys/s)','Total (M ops/s)'],rows,align='llrrrr')
    rows=[]
    for dist in ['uniform','zipfian']:
        for name in ORDER:
            g=get(large,name,dist)
            if not valid(g):continue
            p=float(g.iloc[0].measured_fp_rate);lo,hi=wilson(p)
            low,high=g.measured_fp_rate.min(),g.measured_fp_rate.max()
            interval=f'[{lo*1e3:.4f}, {hi*1e3:.4f}]'
            repeat=f'{low*1e3:.4f}' if low==high else f'{low*1e3:.4f}--{high*1e3:.4f}'
            rows.append([('Uniform' if dist=='uniform' else 'Skewed'),NAMES[name],f'{p*1e3:.4f}',interval,repeat])
    table(out/'tables/accuracy.tex',['Input','Filter','First FPR','95\\% interval','Repeat range'],rows,align='llrrr')
    rows=[]
    for dist in ['uniform','zipfian']:
        for mode,label in [('default','Default'),('invertible','Invertible'),('none','External')]:
            g=hgroup(hashes,mode,dist);p=g.iloc[0].measured_fp_rate;lo,hi=wilson(p)
            rows.append([dist.title(),label,sci(p),f'[{sci(lo)}, {sci(hi)}]',sci(g.iloc[0].theoretical_fp_rate)])
    table(out/'tables/hash_accuracy.tex',['Input','Path','Measured','95\\% interval','Estimate'],rows,align='llrrr')
    rows=[]
    for q in [26,27]:
        g=geom[geom.q==q]
        rows.append([f'$2^{{{q}}}$',f'{g.iloc[0].memory_bytes/1e6:.3f}',sci(g.iloc[0].measured_fp_rate),*[rate(g,c) for c in ['insert_ops_sec','query_pos_ops_sec','query_neg_ops_sec']]])
    table(out/'tables/geometry_control.tex',['Slots','MB','First FPR','Insert','Positive','Negative'],rows)
    rows=[]
    historic=pd.read_csv(ROOT/'results/bench.csv');arch=pd.read_csv(EXT/'paper_scale_1_512.csv')
    paper={'cqf':[11.19,11.16,25.93],'cuckoo':[14.25,18.87,18.84],'bloom':[2.84,2.55,11.56]}
    for source,df in [('Reference paper',None),('Mid-semester',historic),('Archived 67M',arch),('New 67M',large)]:
        for name in ['cqf','cuckoo','bloom']:
            vals=paper[name] if df is None else [stat(get(df,name,'uniform'),c,1e6)[0] for c in ['insert_ops_sec','query_pos_ops_sec','query_neg_ops_sec']]
            rows.append([source,NAMES[name],*[f'{v:.2f}' for v in vals]])
    table(out/'tables/history.tex',['Result source','Filter','Insert','Positive','Negative'],rows,align='llrrr')
    rows=[];mix_records=[]
    for name in ORDER:
        values=[]
        for dist,alpha in [('uniform',.5),('uniform',.9),('zipfian',.5)]:
            value=mixed_query_rate(get(large,name,dist),alpha)
            values.append(fnum(value/1e6))
            mix_records.append({'filter':name,'distribution':dist,'positive_fraction':alpha,'model_queries_per_second':value})
        rows.append([NAMES[name],*values])
    table(out/'tables/query_mix.tex',['Filter','Uniform: 50\\% +','Uniform: 90\\% +','Skewed: 50\\% +'],rows)
    pd.DataFrame(mix_records).to_csv(out/'data/query_mix_model.csv',index=False)
    rows=[]
    for name in ORDER:
        points=[get(raw(tag),name,'uniform').iloc[0] for tag in ['report_67m_256','report_67m','report_67m_1024']]
        rows.append([NAMES[name],*[f'{point.memory_bytes/1e6:.2f}' for point in points],*[f'{point.measured_fp_rate*1e3:.4f}' for point in points]])
    table(out/'tables/target_sweep.tex',['Filter','MB: 256','MB: 512','MB: 1024','FPR: 256','FPR: 512','FPR: 1024'],rows)
    rows=[]
    for dist in ['uniform','zipfian']:
        for name in ORDER:
            g=get(small,name,dist);first=g.iloc[0]
            rows.append([('Uniform' if dist=='uniform' else 'Skewed'),NAMES[name],rate(g,'insert_ops_sec',False),rate(g,'build_ops_sec',False),rate(g,'query_pos_ops_sec',False),rate(g,'query_neg_ops_sec',False),rate(g,'delete_ops_sec',False),f'{first.memory_bytes/1e6:.3f}'])
    table(out/'tables/small_full.tex',['Input','Filter','Insert','Build','Positive','Negative','Delete','MB'],rows,align='llrrrrrr')
    rows=[]
    for scale,df in [('996k',control),('67M',hashes)]:
        for dist in ['uniform','zipfian']:
            for mode,label in [('default','Default'),('invertible','Invertible'),('none','External')]:
                g=hgroup(df,mode,dist)
                rows.append([scale,('Uniform' if dist=='uniform' else 'Skewed'),label,*[rate(g,c,False) for c in ['insert_ops_sec','query_pos_ops_sec','query_neg_ops_sec','delete_ops_sec']]])
    table(out/'tables/hash_full.tex',['Scale','Input','Path','Insert','Positive','Negative','Delete'],rows,align='lllrrrr')

    # Conceptual diagram, drawn as vectors.
    fig,ax=plt.subplots(figsize=(7.0,1.65));ax.set(xlim=(0,10),ylim=(0,2));ax.axis('off')
    boxes=[(.1,.75,1.3,'Original key\nuint64'),(2,.75,1.5,'Hash path\n$p=q+r$ bits'),(4.2,.75,2,'Quotient $q$\nHome slot / run'),(7,.75,2.7,'Remainder $r$\nStored bits and counts')]
    for x,y,w,text in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,.9,boxstyle='round,pad=0.06',fc='#EFF5F6',ec='#147D83',lw=1));ax.text(x+w/2,y+.45,text,ha='center',va='center',fontsize=9)
    for start,end in [(1.5,1.9),(3.6,4.1),(6.3,6.9)]:ax.annotate('',xy=(end,1.2),xytext=(start,1.2),arrowprops=dict(arrowstyle='->',color='#3F6691'))
    ax.text(6.8,.23,'Occupied bits + run-end bits + offsets locate the run',ha='center',fontsize=9,color='#3F6691')
    save(fig,out,'cqf_layout')

    fig,axs=plt.subplots(2,2,figsize=(7.1,4.8),layout='constrained')
    for ax,col,title,names in zip(axs.flat,['insert_ops_sec','query_pos_ops_sec','query_neg_ops_sec','delete_ops_sec'],['Online insertion','Positive lookup','Negative lookup','Known-occurrence deletion'],[ORDER[:5],ORDER,ORDER,['cqf','cuckoo','counting_bloom']]):
        means,sd=zip(*(stat(get(large,f,'uniform'),col,1e6) for f in names))
        y=np.arange(len(names));ax.barh(y,means,color=[COLORS[f] for f in names],height=.62,xerr=sd,error_kw={'lw':.8,'capsize':2})
        ax.set(yticks=y,yticklabels=[NAMES[f] for f in names],title=title,xlabel='Million operations or queries / s');ax.invert_yaxis();ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    save(fig,out,'uniform_operations')

    fig,ax=plt.subplots(figsize=(7.1,3.05),layout='constrained');x=np.arange(len(ORDER))
    for offset,dist,label,alpha in [(-.18,'uniform','Uniform',1),(.18,'zipfian','Skewed',.45)]:
        vals=[get(large,f,dist).iloc[0].memory_bytes/1e6 for f in ORDER]
        bars=ax.bar(x+offset,vals,width=.34,label=label,color=[COLORS[f] for f in ORDER],alpha=alpha)
        if dist=='zipfian':bars[1].set_hatch('////');ax.text(x[1]+offset,vals[1]*1.15,'failed',ha='center',fontsize=8)
    ax.scatter([-.18],[compact.memory_bytes/1e6],marker='D',s=35,color='#233D4D',label='Compact CQF (skewed)',zorder=5)
    ax.set(yscale='log',ylabel='Final filter footprint (decimal MB)',xticks=x,xticklabels=[NAMES[f] for f in ORDER],ylim=(.15,900));ax.tick_params(axis='x',rotation=15);ax.grid(axis='y',alpha=.18);ax.legend(loc='upper right',ncol=2)
    save(fig,out,'skew_space')

    fig,axs=plt.subplots(1,2,figsize=(7.1,2.55),layout='constrained')
    for ax,dist in zip(axs,['uniform','zipfian']):
        for j,f in enumerate(['xor','binary_fuse']):
            g=get(large,f,dist);prep=g.preprocess_time_s.mean();build=pd.to_numeric(g.build_time_s).mean()
            ax.barh(j,prep,color='#B9CED4',label='Preparation' if j==0 else None);ax.barh(j,build,left=prep,color=COLORS[f],label='Build' if j==0 else None)
            ax.text(prep+build+.02*(prep+build),j,f'{prep+build:.2f}s',va='center',fontsize=8)
        ax.set(yticks=[0,1],yticklabels=['XOR','Fuse-style'],xlabel='Mean seconds',title=dist.title());ax.invert_yaxis();ax.set_xlim(0,ax.get_xlim()[1]*1.13);ax.grid(axis='x',alpha=.18)
    axs[0].legend(loc='lower right');save(fig,out,'static_preparation')

    fig,axs=plt.subplots(1,2,figsize=(7.1,3.25),layout='constrained')
    for ax,dist in zip(axs,['uniform','zipfian']):
        names=[f for f in ORDER if valid(get(large,f,dist))]
        for j,f in enumerate(names):
            first=get(large,f,dist).iloc[0];p=float(first.measured_fp_rate);lo,hi=wilson(p)
            ax.errorbar(p,j,xerr=[[p-lo],[hi-p]],fmt='o',color=COLORS[f],capsize=3,ms=5)
            ax.scatter(first.theoretical_fp_rate,j,marker='D',facecolors='none',edgecolors='#233D4D',s=32,zorder=4)
        ax.axvline(1/512,color='#6C7378',linestyle='--',lw=.8);ax.set(xscale='log',yticks=range(len(names)),yticklabels=[NAMES[f] for f in names],xlabel='False-positive probability',title=dist.title());ax.invert_yaxis();ax.grid(axis='x',alpha=.18)
        if dist == 'uniform':
            ax.set_xticks([0.001,0.0015,0.002])
            ax.set_xticklabels(['0.0010','0.0015','0.0020'])
            ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
            ax.set_xlim(0.00085,0.0022)
    save(fig,out,'accuracy_intervals')

    fig,axs=plt.subplots(2,2,figsize=(7.1,4.5),layout='constrained')
    cols=['insert_ops_sec','query_pos_ops_sec','query_neg_ops_sec'];labels=['Insert','Positive','Negative']
    for row,(scale,df) in enumerate([('996k',control),('67M',hashes)]):
        for column,dist in enumerate(['uniform','zipfian']):
            ax=axs[row,column];x=np.arange(3)
            for off,mode,label,color in [(-.17,'invertible','Invertible','#3F6691'),(.17,'none','External SplitMix64','#147D83')]:
                ratios=[];errs=[]
                for col in cols:
                    a,sa=stat(hgroup(df,mode,dist),col);b,sb=stat(hgroup(df,'default',dist),col)
                    ratios.append(a/b);errs.append((a/b)*math.sqrt((sa/a)**2+(sb/b)**2))
                ax.bar(x+off,ratios,width=.32,label=label,color=color,yerr=errs,error_kw={'capsize':2,'lw':.7})
            ax.axhline(1,color='#6C7378',lw=.8,linestyle='--');ax.set(xticks=x,xticklabels=labels,ylabel='Rate / default rate',title=f'{scale} / {dist}');ax.set_ylim(0,max(2.2,ax.get_ylim()[1]));ax.grid(axis='y',alpha=.18)
    axs[0,0].legend(loc='upper left');save(fig,out,'hash_speedups')

    fig,axs=plt.subplots(1,3,figsize=(7.1,3.0),layout='constrained')
    for ax,col,title in zip(axs[:2],['query_pos_ops_sec','query_neg_ops_sec'],['Positive lookup','Negative lookup']):
        y=np.arange(len(ORDER))
        for off,df,label,color in [(-.18,small,'1M','#90B9BF'),(.18,large,'67M','#3F6691')]:
            mu,sd=zip(*(stat(get(df,f,'uniform'),col,1e6) for f in ORDER));ax.barh(y+off,mu,height=.33,xerr=sd,color=color,label=label,error_kw={'lw':.6})
        ax.set(yticks=y,yticklabels=[NAMES[f] for f in ORDER],title=title,xlabel='Million queries / s');ax.invert_yaxis();ax.grid(axis='x',alpha=.18)
    ax=axs[2];y=np.arange(len(ORDER))
    for off,df,label,color in [(-.18,small,'1M','#90B9BF'),(.18,large,'67M','#3F6691')]:ax.barh(y+off,[get(df,f,'uniform').iloc[0].memory_bytes/1e6 for f in ORDER],height=.33,color=color,label=label)
    ax.set(yticks=y,yticklabels=[NAMES[f] for f in ORDER],xscale='log',title='Final footprint',xlabel='Decimal MB');ax.invert_yaxis();ax.grid(axis='x',alpha=.18);axs[0].legend(loc='lower right');save(fig,out,'scale_comparison')

    sweep=[('1/256',raw('report_67m_256')),('1/512',large),('1/1024',raw('report_67m_1024'))]
    fig,axs=plt.subplots(1,2,figsize=(7.1,3.2),layout='constrained')
    for f in ORDER:
        mem=[get(df,f,'uniform').iloc[0].memory_bytes/1e6 for _,df in sweep]
        p=[get(df,f,'uniform').iloc[0].measured_fp_rate for _,df in sweep]
        axs[0].plot(range(3),mem,marker='o',ms=4,color=COLORS[f],label=NAMES[f]);axs[1].plot(range(3),p,marker='o',ms=4,color=COLORS[f])
    axs[1].plot(range(3),[1/256,1/512,1/1024],ls='--',lw=1,color='#233D4D',label='Nominal target')
    for ax in axs:ax.set(xticks=range(3),xticklabels=[label for label,_ in sweep],xlabel='Nominal error target',yscale='log');ax.grid(axis='y',alpha=.18)
    axs[0].set_ylabel('Final footprint (decimal MB)');axs[1].set_ylabel('First-run measured FPR');axs[0].legend(ncol=2,loc='lower left',fontsize=7);axs[1].legend(loc='upper right',fontsize=7)
    save(fig,out,'fpr_sensitivity')

    # Machine-readable summary and evidence copied into the portable project.
    summaries=[]
    for scale,df in [('1m',small),('67m',large)]:
        for dist in ['uniform','zipfian']:
            for f in ORDER:
                g=get(df,f,dist);r={'scale':scale,'filter':f,'distribution':dist,'status':'complete' if valid(g) else 'capacity_failure','memory_bytes':int(g.iloc[0].memory_bytes)}
                for col in ['insert_ops_sec','build_ops_sec','query_pos_ops_sec','query_neg_ops_sec','delete_ops_sec']:
                    mu,sd=stat(g,col);r[col+'_mean']=mu;r[col+'_sd']=sd
                summaries.append(r)
    pd.DataFrame(summaries).to_csv(out/'data/report_summary.csv',index=False)
    for p in EXT.glob('*report*'):
        if p.is_file() and p.suffix in ['.csv','.txt']:shutil.copy2(p,out/'data'/p.name)
    for p in REPORT.iterdir():
        if p.is_file():shutil.copy2(p,out/('data' if p.suffix=='.csv' else 'reproducibility')/p.name)
    for src,dst in [(ROOT/'results/bench.csv','archived_bench.csv'),(EXT/'paper_scale_1_512.csv','archived_paper_scale_1_512.csv')]:shutil.copy2(src,out/'data'/dst)
    shutil.copy2(ROOT/'docs/REPORT_AUDIT.md',out/'reproducibility/REPORT_AUDIT.md')
    print('Generated report assets:',out)
    print(json.dumps(macros,indent=2))

if __name__=='__main__':main()
