"""Make reviewable tables and native-resolution boards from measured evidence."""
from pathlib import Path
import argparse
import csv
import json

import numpy as np
from PIL import Image, ImageDraw


def summarize(root):
    root=Path(root)
    data=json.loads((root/'metrics.json').read_text())
    rows=[]
    for name,profile in data['profiles'].items():
        frames=profile['frames']
        q=[f['passes']['before']['underwater']['fixed_quality'] for f in frames]
        raw=[f['passes']['before']['raw']['fixed_quality'] for f in frames]
        s=[f['passes']['before']['underwater']['fixed_stereo'] for f in frames]
        consistency=[f['consistency']['underwater'] for f in frames]
        rows.append({'profile':name,'mean_fixed_raw_y':np.mean([x['mean_y'] for x in raw]),
                     'mean_fixed_uw_y':np.mean([x['mean_y'] for x in q]),
                     'raw_dark_lt10_fraction':np.mean([x['dark_y_lt10'] for x in raw]),
                     'uw_dark_lt20_fraction':np.mean([x['dark_y_lt20'] for x in q]),
                     'raw_channel_clip_fraction':np.mean([x['any_channel_ge250'] for x in raw]),
                     'uw_channel_clip_fraction':np.mean([x['any_channel_ge250'] for x in q]),
                     'uw_local_std7':np.mean([x['local_std7'] for x in q]),
                     'uw_gradient_mean':np.mean([x['gradient_mean'] for x in q]),
                     'mean_fixed_detections_left':np.mean([x['detections_left'] for x in s]),
                     'fixed_gt_matches_min':min(x['gt_valid_matches'] for x in s),
                     'fixed_gt_matches_max':max(x['gt_valid_matches'] for x in s),
                     'mean_repeatability':np.mean([x['fixed']['repeatability'] for x in consistency]),
                     'fixed_pass_mae_y':np.mean([x['fixed']['mae_y'] for x in consistency]),
                     'crate_region_pass_mae_y':np.mean([x['change_region_mae_y'] for x in consistency])})
    with (root/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    selected=Path(data['profiles']['recommended']['run'])
    baseline=Path(data['profiles']['baseline']['run'])
    board=Image.new('RGB',(4*752,2*512),'#101820')
    draw=ImageDraw.Draw(board)
    for i,frame in enumerate((0,59)):
        for j,(session,side) in enumerate((('before','left'),('before','right'),('after','left'),('after','right'))):
            draw.text((j*752+8,i*512+8),f'Selected | {session} {side} | original frame {frame}',fill='white')
            board.paste(Image.open(selected/session/side/f'{frame:06d}.png').convert('RGB'),(j*752,i*512+32))
    board.save(root/'matched_stereo_before_after.png')
    board=Image.new('RGB',(3*752,2*512),'#101820')
    draw=ImageDraw.Draw(board)
    for i,(name,run) in enumerate((('original',baseline),('selected',selected))):
        paths=[run/'photometry/before_000000_left_raw.png',run/'before/left/000000.png',run/'after/left/000000.png']
        for j,(label,path) in enumerate(zip(('Raw RTX before OceanSim','Processed before','Processed after'),paths)):
            draw.text((j*752+8,i*512+8),f'{name} | {label} | original frame 0',fill='white')
            board.paste(Image.open(path).convert('RGB'),(j*752,i*512+32))
    board.save(root/'baseline_vs_selected.png')
    print(root/'summary.csv')
    print(root/'matched_stereo_before_after.png')
    print(root/'baseline_vs_selected.png')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',nargs='?',default='outputs/photometric_6_1')
    summarize(parser.parse_args().root)
