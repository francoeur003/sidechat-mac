"""Conservative geometry detector for light-mode WeChat desktop chat panes.

Find persistent vertical panel edges, a header divider and a blank composer below
its top border. Never infer a crop from a screen percentage alone. Ambiguous or
unsupported screens fail closed. Coordinates are relative to the captured window.
"""
import numpy as np
from chat_region import Region

class AutoRegionError(ValueError):pass

def _groups(values,gap=8):
    groups=[]
    for v in values:
        v=int(v)
        if groups and v-groups[-1][-1]<=gap:groups[-1].append(v)
        else:groups.append([v])
    return groups

def detect_region(pixels,point_width):
    if pixels.ndim!=3 or pixels.shape[2]<3 or point_width<=0:
        raise AutoRegionError('无法定位聊天区域，请打开微信对话')
    scale=pixels.shape[1]/point_width
    step=max(1,round(scale))
    rgb=pixels[::step,::step,:3].astype(np.float32)
    h,w=rgb.shape[:2];gray=rgb.mean(axis=2)
    unit=scale/step
    if w<480*unit or h<350*unit:
        raise AutoRegionError('微信窗口太小，请放大后打开对话')
    y0,y1=int(h*.14),int(h*.72)
    xs=[]
    for x in range(round(160*unit),w-round(220*unit)):
        left=np.median(gray[y0:y1,x-4:x],axis=1)
        right=np.median(gray[y0:y1,x+1:x+5],axis=1)
        if np.mean(np.abs(left-right)>5)>.72:xs.append(x)
    edges=[round(float(np.median(g))) for g in _groups(xs)]+[w-4]
    candidates=[]
    for left,right in zip(edges,edges[1:]):
        if right-left<220*unit:continue
        a,b=left+round(12*unit),right-round(12*unit)
        # The chat and editor surfaces in the supported light layout are almost white.
        if np.median(gray[y0:y1,a:b])<246:continue
        section=gray[:,a:b]
        local_max=np.maximum.reduce([section[:-4],section[1:-3],section[2:-2],section[3:-1],section[4:]])
        local_min=np.minimum.reduce([section[:-4],section[1:-3],section[2:-2],section[3:-1],section[4:]])
        horizontal=np.flatnonzero(np.mean(local_max-local_min>6,axis=1)>.80)+2
        groups=_groups(horizontal,gap=4)
        headers=[g for g in groups if 28*unit<=np.median(g)<=110*unit]
        bottoms=[g for g in groups if max(h*.45,h-300*unit)<=np.median(g)<=h-80*unit]
        # Messages can contain an image with horizontal rules near the header.
        # The first divider starts the chat; later rules belong to its content.
        if not headers:continue
        # A busy area below the first plausible divider is not a blank composer.
        # Do not skip it and reinterpret the bottom edge of its content as an editor.
        for bottom in bottoms[:1]:
            top=headers[0][-1]+1;end=bottom[0]-1
            if end-top<160*unit:continue
            editor=rgb[bottom[-1]+round(14*unit):h-round(48*unit),a:b]
            if editor.size==0:continue
            clean=(editor.min(axis=2)>=246)&(np.ptp(editor,axis=2)<8)
            if np.mean(clean)<.965:continue
            candidates.append(Region(left/w,top/h,right/w,end/h))
            break
    if len(candidates)!=1:
        raise AutoRegionError('未能确定聊天区域，请打开微信对话或点「调整范围」')
    return candidates[0]
