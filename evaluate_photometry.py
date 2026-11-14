"""Offline target-free photometry, depth-verified SIFT stereo and pass consistency.

Requires NumPy, OpenCV and Pillow in ordinary Python, never imported by Kit.
Metrics use lossless images. No photometric normalization or image enhancement.
"""
from pathlib import Path
import argparse
import csv
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw


def read_json(path):
    return json.loads(Path(path).read_text())


def poses(run, session):
    return {r['frame']: r for r in map(json.loads, (run / session / 'poses.jsonl').read_text().splitlines())}


def luminance(rgb):
    return np.asarray(rgb[..., :3], np.float32) @ np.array([.2126, .7152, .0722], np.float32)


def quality(rgb, mask):
    y = luminance(rgb)
    x = y[mask]
    if not x.size:
        return {'pixels': 0}
    local_var = np.maximum(0, cv2.blur(y*y, (7, 7)) - cv2.blur(y, (7, 7))**2)
    gx = cv2.Sobel(y, cv2.CV_32F, 1, 0, ksize=3) / 8
    gy = cv2.Sobel(y, cv2.CV_32F, 0, 1, ksize=3) / 8
    return {'pixels': int(x.size), 'mean_y': float(x.mean()), 'median_y': float(np.median(x)),
            'p05_y': float(np.percentile(x, 5)), 'p95_y': float(np.percentile(x, 95)),
            'dark_y_lt10': float((x < 10).mean()), 'saturated_y_ge250': float((x >= 250).mean()),
            'dark_y_lt20': float((x < 20).mean()),
            'any_channel_ge250': float((rgb[..., :3][mask] >= 250).any(axis=1).mean()),
            'local_std7': float(np.sqrt(local_var)[mask].mean()),
            'gradient_mean': float(np.hypot(gx, gy)[mask].mean())}


def points(depth, k, transform):
    yy, xx = np.indices(depth.shape)
    rays = np.stack([(xx+.5-k[0,2])/k[0,0], (yy+.5-k[1,2])/k[1,1], np.ones_like(xx)], -1)
    finite_depth = np.where(np.isfinite(depth), depth, -10000.)
    xyz = rays * (finite_depth / np.linalg.norm(rays, axis=-1))[..., None]
    return xyz @ transform[:3,:3].T + transform[:3,3]


def equipment_mask(depth, k, transform, bounds):
    xyz = points(depth, k, transform)
    mask = np.zeros(depth.shape, bool)
    for low, high in bounds.values():
        mask |= ((xyz >= np.array(low)-.012) & (xyz <= np.array(high)+.012)).all(axis=-1)
    return cv2.erode(mask.astype('uint8'), np.ones((3,3), np.uint8)).astype(bool)


def change_mask(shape, k, transform, cfg):
    mask = np.zeros(shape, np.uint8)
    for offset in (np.zeros(3), np.array(cfg['changes']['displacement_m'])):
        center = np.array(cfg['changes']['before_position_m']) + offset
        corners = np.array([center + np.array([x,y,z]) for x in (-.34,.34) for y in (-.26,.26) for z in (-.32,.35)])
        opt = (corners-transform[:3,3]) @ transform[:3,:3]
        uv = opt @ k.T
        uv = uv[:,:2]/uv[:,2:]
        cv2.fillConvexPoly(mask, cv2.convexHull(np.rint(uv).astype('int32')), 1)
    return cv2.dilate(mask, np.ones((9,9), np.uint8)).astype(bool)


SIFT = cv2.SIFT_create(nfeatures=1800, contrastThreshold=.02, edgeThreshold=10)
MATCHER = cv2.BFMatcher(cv2.NORM_L2)


def features(rgb, mask):
    # Same detector and thresholds for every condition; SIFT uses normal RGB gray.
    return SIFT.detectAndCompute(cv2.cvtColor(rgb[...,:3], cv2.COLOR_RGB2GRAY), mask.astype('uint8')*255)


def reciprocal(a, b):
    ka, da = a
    kb, db = b
    if da is None or db is None or min(len(da),len(db)) < 2:
        return []
    forward = {m.queryIdx:m for pair in MATCHER.knnMatch(da, db, k=2) if len(pair)==2
               for m,n in [pair] if m.distance < .75*n.distance}
    reverse = {m.queryIdx:m.trainIdx for pair in MATCHER.knnMatch(db, da, k=2) if len(pair)==2
               for m,n in [pair] if m.distance < .75*n.distance}
    return [m for m in forward.values() if reverse.get(m.trainIdx)==m.queryIdx]


def stereo_metrics(left, right, depths, k, transforms, masks):
    a,b = features(left,masks[0]),features(right,masks[1])
    matches = reciprocal(a,b)
    valid, errors, depths_z = [], [], []
    h,w = depths[0].shape
    for m in matches:
        u,v = a[0][m.queryIdx].pt
        ur,vr = b[0][m.trainIdx].pt
        x,y = np.clip(np.rint([u,v]).astype(int), [0,0], [w-1,h-1])
        if not np.isfinite(depths[0][y,x]) or depths[0][y,x]<=0:
            continue
        ray = np.array([(u-k[0,2])/k[0,0], (v-k[1,2])/k[1,1], 1.])
        optical = ray * (depths[0][y,x]/np.linalg.norm(ray))
        world = transforms[0][:3,:3] @ optical + transforms[0][:3,3]
        opt_right = transforms[1][:3,:3].T @ (world-transforms[1][:3,3])
        predicted = k @ opt_right
        predicted = predicted[:2]/predicted[2]
        err = float(np.linalg.norm(predicted-[ur,vr]))
        xr,yr = np.clip(np.rint([ur,vr]).astype(int), [0,0], [w-1,h-1])
        range_ok = abs(np.linalg.norm(opt_right)-depths[1][yr,xr]) <= max(.08,.015*np.linalg.norm(opt_right))
        disparity = u-ur
        baseline = np.linalg.norm(transforms[0][:3,3]-transforms[1][:3,3])
        z_stereo = k[0,0]*baseline/disparity if disparity>0 else -1
        if err <= 2 and abs(v-vr)<=1 and range_ok and abs(z_stereo/optical[2]-1)<=.1:
            valid.append(m)
            errors.append(err)
            depths_z.append(float(optical[2]))
    cells = {(min(7,int(a[0][m.queryIdx].pt[0]*8/w)),min(4,int(a[0][m.queryIdx].pt[1]*5/h))) for m in valid}
    return {'detections_left':len(a[0]), 'detections_right':len(b[0]), 'reciprocal_ratio_matches':len(matches),
            'gt_valid_matches':len(valid), 'gt_precision':len(valid)/len(matches) if matches else 0.,
            'occupied_cells_8x5':len(cells), 'median_gt_error_px':float(np.median(errors)) if errors else None,
            'valid_optical_z_min_m':min(depths_z) if depths_z else None,
            'valid_optical_z_max_m':max(depths_z) if depths_z else None}, (a,b,valid)


def session_metrics(before, after, mask):
    a,b = features(before,mask),features(after,mask)
    matches = reciprocal(a,b)
    good = [m for m in matches if np.linalg.norm(np.array(a[0][m.queryIdx].pt)-b[0][m.trainIdx].pt)<=2]
    delta = np.abs(luminance(before)-luminance(after))[mask]
    return {'detections_before':len(a[0]),'detections_after':len(b[0]),
            'same_pose_repeatable_matches':len(good),
            'repeatability':len(good)/min(len(a[0]),len(b[0])) if min(len(a[0]),len(b[0])) else 0.,
            'mae_y':float(delta.mean()), 'p95_abs_y':float(np.percentile(delta,95)),
            'fraction_abs_y_gt10':float((delta>10).mean())}


def evaluate(root, selected=None):
    root = Path(root)
    runs = {}
    for status in root.glob('*/*/status.json'):
        run = status.parent
        if selected and run.parent.name not in selected:
            continue
        if read_json(status)['state']=='complete' and (run/'photometry').is_dir():
            runs[run.parent.name] = run
    bounds = next(read_json(r/'photometry/scene_evidence.json')['equipment_bounds'] for r in runs.values()
                  if read_json(r/'photometry/scene_evidence.json').get('equipment_bounds'))
    report = {'method': {'detector':'OpenCV SIFT, 1800 cap, contrast .02, mutual ratio .75',
                        'stereo_gate':'Known radial range reprojection <=2px, epipolar <=1px, positive disparity, right visibility <=max(.08m,1.5%), stereo Z within10%',
                        'fixed_mask':'Visible range points in original equipment AABBs +/-12mm; erode1px; exclude union of both projected moved-crate bounds +4px',
                        'luminance':'Rec709 weights on 8-bit RGB code values, not physical luminance',
                        'repeatability':'Same-pose reciprocal SIFT with <=2px coordinate drift; count/min detections',
                        'caution':'Geometric gates bound incorrect matches but repeated pipes may remain ambiguous; this is not SLAM validation'}, 'profiles':{}}
    contact = []
    for name,run in runs.items():
        cache = run/'photometry/metrics_v2.json'
        if cache.exists():
            report['profiles'][name] = read_json(cache)
            with np.load(run/'photometry/before_000000.npz') as a, np.load(run/'photometry/after_000000.npz') as b:
                contact.append((name,a['left_raw_rgba'],a['left_underwater_rgba'],b['left_underwater_rgba']))
            continue
        cfg = read_json(run/'config.json')
        cal = read_json(run/'stereo_calibration.json')
        k = np.array(cal['K']['left'])
        bp,ap = poses(run,'before'),poses(run,'after')
        assert bp.keys()==ap.keys(), name
        for frame in bp:
            for key in ('T_world_body','T_world_optical'):
                if key=='T_world_optical':
                    for s in ('left','right'):
                        assert np.allclose(bp[frame][key][s],ap[frame][key][s],atol=1e-9), name
                else:
                    assert np.allclose(bp[frame][key],ap[frame][key],atol=1e-9), name
            assert np.allclose(np.array(ap[frame]['T_world_changed_object'])[:3,3]-np.array(bp[frame]['T_world_changed_object'])[:3,3], cfg['changes']['displacement_m'])
        frames = []
        for path in sorted((run/'photometry').glob('before_*.npz')):
            frame = int(path.stem.split('_')[1])
            before,after = np.load(path),np.load(path.with_name(path.name.replace('before','after')))
            transforms = [np.array(bp[frame]['T_world_optical'][s]) for s in ('left','right')]
            change = [change_mask(before['left_clean_range_m'].shape,k,t,cfg) for t in transforms]
            row = {'frame':frame, 'passes':{}, 'consistency':{}}
            for session,arrays,pose in [('before',before,bp[frame]),('after',after,ap[frame])]:
                depth = [arrays[f'{s}_clean_range_m'] for s in ('left','right')]
                fixed = [equipment_mask(d,k,t,bounds) & ~c for d,t,c in zip(depth,transforms,change)]
                entry = {}
                for domain in ('raw','underwater'):
                    images = [arrays[f'{s}_{domain}_rgba'] for s in ('left','right')]
                    metrics,drawdata = stereo_metrics(*images,depth,k,transforms,fixed)
                    allmetrics,_ = stereo_metrics(*images,depth,k,transforms,[~c for c in change])
                    entry[domain] = {'fixed_quality':quality(images[0],fixed[0]),
                                     'image_quality':quality(images[0],np.ones(depth[0].shape,bool)),
                                     'fixed_stereo':metrics, 'background_stereo':allmetrics}
                    if session=='before' and domain=='underwater' and frame in (0,59):
                        a,b,valid = drawdata
                        visual = cv2.drawMatches(images[0][...,:3],a[0],images[1][...,:3],b[0],valid,None,
                                                 matchColor=(50,240,80),flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
                        Image.fromarray(visual).save(run/'photometry'/f'matches_{frame:06d}.png')
                        Image.fromarray(fixed[0].astype('uint8')*255).save(run/'photometry'/f'fixed_mask_{frame:06d}.png')
                row['passes'][session] = entry
            for domain in ('raw','underwater'):
                d0,d1 = before['left_clean_range_m'],after['left_clean_range_m']
                visible = np.isfinite(d0) & np.isfinite(d1) & (np.abs(np.nan_to_num(d0)-np.nan_to_num(d1))<.03) & ~change[0]
                fixed = equipment_mask(d0,k,transforms[0],bounds) & equipment_mask(d1,k,transforms[0],bounds) & visible
                images = [x[f'left_{domain}_rgba'] for x in (before,after)]
                row['consistency'][domain] = {'fixed':session_metrics(*images,fixed),
                                               'background':session_metrics(*images,visible),
                                               'change_region_mae_y':float(np.abs(luminance(images[0])-luminance(images[1]))[change[0]].mean())}
            frames.append(row)
            if frame==0:
                contact.append((name, before['left_raw_rgba'],before['left_underwater_rgba'],after['left_underwater_rgba']))
        report['profiles'][name]={'run':str(run),'calibration_and_poses_identical':True,'frames':frames}
        cache.write_text(json.dumps(report['profiles'][name],indent=2,allow_nan=False))
        print(name, ' | '.join(f"{f['frame']}: fixedY={f['passes']['before']['underwater']['fixed_quality']['mean_y']:.1f}, gt={f['passes']['before']['underwater']['fixed_stereo']['gt_valid_matches']}, repeat={f['consistency']['underwater']['fixed']['repeatability']:.2f}, MAE={f['consistency']['underwater']['fixed']['mae_y']:.2f}" for f in frames))
    (root/'metrics.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    canvas = Image.new('RGB',(3*752, len(contact)*(480+32)), '#101820')
    draw = ImageDraw.Draw(canvas)
    for i,(name,*imgs) in enumerate(contact):
        for j,(label,img) in enumerate(zip(('raw RTX before','OceanSim before','OceanSim after'),imgs)):
            draw.text((j*752+8,i*512+8),f'{name} | {label} | frame 0',fill='white')
            canvas.paste(Image.fromarray(img[...,:3]),(j*752,i*512+32))
    canvas.save(root/'controlled_comparisons.png')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',nargs='?',default='outputs/photometric_6_1')
    parser.add_argument('--profiles', nargs='+')
    args=parser.parse_args()
    evaluate(args.root,args.profiles)
