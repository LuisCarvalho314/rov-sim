"""CPU USD audit; use Isaac Sim bundled Python, without starting SimulationApp."""
from pathlib import Path
import argparse
import json
import os
import sys

# USD is an extension, rather than a normal bundled-Python site package.
usd_extensions=list((Path(os.environ['ISAAC_PATH'])/'extscache').glob('omni.usd.libs-*'))
if len(usd_extensions)!=1:
    raise RuntimeError('Expected one installed USD library extension')
sys.path.insert(0,str(usd_extensions[0]))
usd_dll_directory=os.add_dll_directory(str(usd_extensions[0]/'bin'))
from pxr import Usd


def protected(stage):
    result={}
    for prim in stage.Traverse():
        path=str(prim.GetPath())
        if not (path.startswith(('/World/Tank/','/World/FixedEquipment/','/World/Changes/'))
                or '/StereoRig' in path):
            continue
        result[path]={'type':prim.GetTypeName(),
                      'attributes':{a.GetName():repr(a.Get()) for a in prim.GetAttributes() if a.GetName()!='exposure:iso'},
                      'relationships':{r.GetName():[str(p) for p in r.GetTargets()] for r in prim.GetRelationships()}}
    return result


def verify(root):
    root=Path(root)
    runs={name:next((root/name).glob('*/tank_before_rtx.usda')) for name in ('baseline','recommended','recommended_repeat')}
    original=protected(Usd.Stage.Open(str(runs['baseline']),Usd.Stage.LoadNone))
    counts={}
    exposures={}
    for name,path in runs.items():
        stage=Usd.Stage.Open(str(path),Usd.Stage.LoadNone)
        actual=protected(stage)
        exposures[name]={str(p.GetPath()):p.GetAttribute('exposure:iso').Get() for p in stage.Traverse()
                         if p.GetTypeName()=='Camera' and '/StereoRig/' in str(p.GetPath())}
        expected=json.loads((path.parent/'config.json').read_text())['rtx']['settings'].get('/rtx/post/tonemap/filmIso',100.0)
        assert len(exposures[name])==2 and all(v==expected for v in exposures[name].values())
        if original!=actual:
            differences={}
            for prim in original.keys() | actual.keys():
                if original.get(prim)!=actual.get(prim):
                    a,b=original.get(prim,{}).get('attributes',{}),actual.get(prim,{}).get('attributes',{})
                    differences[prim]={key:[str(a.get(key))[:160],str(b.get(key))[:160]] for key in a.keys() | b.keys() if a.get(key)!=b.get(key)}
            raise AssertionError(json.dumps({'profile':name,'differences':differences}))
        counts[name]=len(actual)
    result={'status':'PASS','protected_prim_counts':counts,
            'approved_camera_exposure_iso':exposures,
            'comparison':'Exact USD types, default attributes and relationship targets of tank, fixed equipment, movable-crate subtree and stereo rig at initial before pose, except exposure:iso. Both camera ISOs are separately verified against the configured exposure; all geometric/calibration attributes must match exactly.'}
    (root/'scene_preservation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',nargs='?',default='outputs/photometric_6_1')
    verify(parser.parse_args().root)
