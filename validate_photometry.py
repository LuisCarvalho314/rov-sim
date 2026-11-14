"""Validate saved target-free evidence and quantify independent-run stability."""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
from PIL import Image

from evaluate_photometry import (read_json, poses, luminance, equipment_mask, change_mask,
                                 features, reciprocal, session_metrics, stereo_metrics)


def only_run(path):
    runs = [p.parent for p in Path(path).glob('*/status.json') if read_json(p)['state']=='complete']
    assert len(runs)==1, str(path)
    return runs[0]


def verify_saved(run):
    cfg = read_json(run/'config.json')
    cal = read_json(run/'stereo_calibration.json')
    assert not read_json(run/'photometry/scene_evidence.json')['target_present']
    max_error = 0.
    checked = 0
    for path in sorted((run/'photometry').glob('*.npz')):
        session, index = path.stem.split('_')
        data = np.load(path)
        meta = read_json(path.with_name(path.stem+'_metadata.json'))
        assert meta['aa_readback']==cfg['rtx'].get('antialiasing',0)
        assert meta['reference_time']['left']==meta['reference_time']['right']
        for side in ('left','right'):
            raw,depth,uw=(data[f'{side}_{field}'] for field in ('raw_rgba','clean_range_m','underwater_rgba'))
            assert np.array_equal(np.array(Image.open(run/session/side/f'{int(index):06d}.png')),uw)
            assert np.array_equal(raw[...,3],uw[...,3])
            # Installed UW_render_2 uses metre stage scale=1, uint8 truncation.
            with np.errstate(over='ignore',invalid='ignore'):
                atten=np.exp(-depth[...,None]*np.array(cfg['underwater']['atten_coeff']))
                back=np.exp(-depth[...,None]*np.array(cfg['underwater']['backscatter_coeff']))
                expected=raw[...,:3]*atten+255*np.array(cfg['underwater']['backscatter_value'])*(1-back)
            valid=np.isfinite(expected).all(axis=-1)
            error=float(np.abs(np.clip(expected[valid],0,255)-uw[...,:3][valid]).max())
            assert error<=1.01, (path,side,error)
            max_error=max(max_error,error)
            checked+=1
    return {'saved_views_checked':checked,'max_underwater_equation_error_levels':max_error,
            'png_equals_processed_buffer':True,'synchronized_reference_time':True,
            'aa_persisted':True,'target_absent':True}


def validate(root, checks_root=None):
    root=Path(root)
    checks_root=Path(checks_root) if checks_root else root/'checks'
    selected=only_run(root/'recommended')
    repeat=only_run(root/'recommended_repeat')
    baseline=only_run(root/'baseline')
    original=read_json('configs/tank_photometric_baseline.yaml')
    cfg=read_json(selected/'config.json')
    cal=read_json(selected/'stereo_calibration.json')
    assert cal==read_json(baseline/'stereo_calibration.json')==read_json(repeat/'stereo_calibration.json')
    for section in ('tank','robot','stereo','underwater','water','changes','experiment'):
        assert cfg[section]==original[section],section
    k=np.array(cal['K']['left'])
    bounds=read_json(selected/'photometry/scene_evidence.json')['equipment_bounds']
    bp,ap,rp=poses(selected,'before'),poses(selected,'after'),poses(repeat,'before')
    for index in bp:
        assert bp[index]['T_world_body']==ap[index]['T_world_body']==rp[index]['T_world_body']
        assert bp[index]['T_world_optical']==ap[index]['T_world_optical']==rp[index]['T_world_optical']
    rows=[]
    for path in sorted((selected/'photometry').glob('before_*.npz')):
        index=int(path.stem.split('_')[1])
        a,b,r=np.load(path),np.load(path.with_name(path.name.replace('before','after'))),np.load(repeat/'photometry'/path.name)
        transforms=[np.array(bp[index]['T_world_optical'][s]) for s in ('left','right')]
        depths=[a[f'{s}_clean_range_m'] for s in ('left','right')]
        masks=[equipment_mask(d,k,t,bounds)&~change_mask(d.shape,k,t,cfg) for d,t in zip(depths,transforms)]
        _, adata=stereo_metrics(a['left_underwater_rgba'],a['right_underwater_rgba'],depths,k,transforms,masks)
        bd=[b[f'{s}_clean_range_m'] for s in ('left','right')]
        bm=[equipment_mask(d,k,t,bounds)&~change_mask(d.shape,k,t,cfg) for d,t in zip(bd,transforms)]
        _, bdata=stereo_metrics(b['left_underwater_rgba'],b['right_underwater_rgba'],bd,k,transforms,bm)
        good_a={m.queryIdx for m in adata[2]}
        good_b={m.queryIdx for m in bdata[2]}
        stable=[m for m in reciprocal(adata[0],bdata[0]) if m.queryIdx in good_a and m.trainIdx in good_b
                and np.linalg.norm(np.array(adata[0][0][m.queryIdx].pt)-bdata[0][0][m.trainIdx].pt)<=2]
        independent=session_metrics(a['left_underwater_rgba'],r['left_underwater_rgba'],masks[0])
        rows.append({'frame':index,'independent_before_repeat':independent,
                     'stereo_valid_feature_repeats':len(stable),'stereo_valid_before':len(adata[2]),
                     'stereo_valid_after':len(bdata[2]),
                     'stereo_valid_repeatability':len(stable)/min(len(adata[2]),len(bdata[2])) if min(len(adata[2]),len(bdata[2])) else 0})
    noise={}
    for name in ('stationary_baseline','stationary_selected'):
        run=only_run(checks_root/name)
        data=np.load(run/'photometry/before_000015.npz')
        pose=poses(run,'before')[0]
        mask=equipment_mask(data['left_clean_range_m'],k,np.array(pose['T_world_optical']['left']),bounds)
        stack=np.stack([luminance(np.array(Image.open(p))) for p in sorted((run/'before/left').glob('*.png'))])
        temporal=stack[5:].std(axis=0)[mask]
        step=np.abs(np.diff(stack[5:],axis=0))[:,mask]
        noise[name]={'frames_used':'5..19; fixed camera, original animated water',
                     'mean_temporal_std_y':float(temporal.mean()),'p95_temporal_std_y':float(np.percentile(temporal,95)),
                     'mean_consecutive_abs_y':float(step.mean()),'p95_consecutive_abs_y':float(np.percentile(step,95))}
    hashes=[]
    extension=Path(read_json(selected/'status.json')['extension']['extension_directory'])
    pinned = Path(__file__).parent/'third_party/OceanSim'
    manifest = ('oceansim_source_hashes.json' if extension.resolve() == pinned.resolve()
                else 'photometric_oceansim_hashes.json')
    for item in read_json(Path(__file__).parent/'docs'/manifest):
        source=extension/item['relative_path']
        content = source.read_bytes()
        if manifest == 'oceansim_source_hashes.json':
            content = content.replace(b'\r\n', b'\n')
        actual=hashlib.sha256(content).hexdigest()
        assert actual==item['sha256'],str(source)
        hashes.append({'path':str(source),'sha256':actual})
    result={'status':'PASS','original_scene_calibration_trajectory_water_and_kernels_preserved':True,
            'selected':verify_saved(selected),'repeat':verify_saved(repeat),
            'independent_run_and_stereo_repeatability':rows,'stationary_temporal_variation':noise,
            'unchanged_oceansim_files':hashes}
    (root/'verification.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='unchanged_oceansim_files'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',nargs='?',default='outputs/photometric_6_1')
    parser.add_argument('--checks-root')
    args=parser.parse_args()
    validate(args.root,args.checks_root)
