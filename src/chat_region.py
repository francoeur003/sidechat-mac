"""Window-relative calibration and local bubble geometry (no chat data is stored)."""
from __future__ import annotations

import ctypes
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


REGION_PATH = Path.home() / ".config/jev-jarvis/region.json"
import os
if os.environ.get("SIDECHAT_MODE") == "1":
    from sidechat_providers import CONFIG_DIR
    REGION_PATH = CONFIG_DIR / "region.json"



@dataclass(frozen=True)
class Region:
    left: float
    top: float
    right: float
    bottom: float

    def as_dict(self):
        return dict(left=self.left, top=self.top, right=self.right, bottom=self.bottom)


def load_region(width, height, path=None):
    """A resize requires re-selection: silently scaling a sidebar crop is unsafe."""
    path = path or REGION_PATH
    if not path.exists():
        raise ValueError("请点右上角「框选范围」，只框住聊天记录")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        r = Region(*(float(data[k]) for k in ("left", "top", "right", "bottom")))
        if not all(np.isfinite(v) for v in r.as_dict().values()):
            raise ValueError()
        if not (0 <= r.left < r.right <= 1 and 0.015 <= r.top < r.bottom <= 1):
            raise ValueError()
        if (r.right-r.left)*width < 100 or (r.bottom-r.top)*height < 80:
            raise ValueError()
        if abs(float(data["width"])-width) > 2 or abs(float(data["height"])-height) > 2:
            raise ValueError("微信窗口尺寸变了，请重新框选聊天区域")
        return r
    except ValueError as exc:
        if str(exc).startswith("微信"):
            raise
        raise ValueError("识别区域设置无效，请重新框选聊天区域") from exc
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError("识别区域设置无效，请重新框选聊天区域") from exc


def image_pixels(image):
    import Quartz as Q
    w, h = Q.CGImageGetWidth(image), Q.CGImageGetHeight(image)
    buf = ctypes.create_string_buffer(w*h*4)
    ctx = Q.CGBitmapContextCreate(buf,w,h,8,w*4,Q.CGColorSpaceCreateDeviceRGB(),
                                Q.kCGImageAlphaPremultipliedLast)
    Q.CGContextDrawImage(ctx,Q.CGRectMake(0,0,w,h),image)
    return np.frombuffer(buf.raw,dtype=np.uint8).reshape(h,w,4).copy()


def _components(mask):
    """Connected row runs; much cheaper than a Python visit for every bubble pixel."""
    parents, boxes, previous = [], [], []
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False]))
        current = []
        for x0, x1 in zip(edges[::2], edges[1::2]):
            overlap = {root(i) for a,b,i in previous if a < x1 and b > x0}
            if not overlap:
                i = len(parents); parents.append(i); boxes.append([x0,y,x1,y+1,x1-x0])
            else:
                i = min(overlap)
                for j in overlap - {i}:
                    parents[j] = i
                    a,b,c,d,n = boxes[j]
                    v = boxes[i]
                    boxes[i] = [min(v[0],a),min(v[1],b),max(v[2],c),max(v[3],d),v[4]+n]
                v = boxes[i]
                boxes[i] = [min(v[0],x0),v[1],max(v[2],x1),y+1,v[4]+x1-x0]
            current.append((x0,x1,i))
        previous = current
    return [box for i,box in enumerate(boxes) if root(i) == i]


def bubble_boxes(pixels, region, point_width=None):
    """Only solid, side-aligned native text bubbles; stickers/cards are not text turns."""
    h,w = pixels.shape[:2]
    scale = w / (point_width or w)
    x0,y0,x1,y1 = int(region.left*w),int(region.top*h),int(region.right*w),int(region.bottom*h)
    rgb = pixels[y0:y1,x0:x1,:3].astype(np.int16)
    if not rgb.size:
        return []
    # Native light-mode WeChat: neutral incoming bubbles, green outgoing bubbles.
    neutral = (rgb.min(axis=2) >= 230) & (rgb.max(axis=2) <= 244) & (np.ptp(rgb,axis=2) <= 7)
    green = (rgb[:,:,1] > rgb[:,:,0]+25) & (rgb[:,:,1] > rgb[:,:,2]+25) & (rgb[:,:,1] > 160)
    found = []
    for side, mask in (("them",neutral),("me",green)):
        for a,b,c,d,n in _components(mask):
            bw,bh = c-a,d-b
            if bw < 24*scale or bh < 23*scale or n/(bw*bh) < .55:
                continue
            if bh > (y1-y0)*.85 or (side == "them" and a > (x1-x0)*.28):
                continue
            if side == "me" and x1-x0-c > (x1-x0)*.28:
                continue
            found.append((side,(a+x0)/w,(b+y0)/h,(c+x0)/w,(d+y0)/h))
    return sorted(found,key=lambda b:b[2])


def latest_avatar_top(pixels, region, point_width):
    """An avatar below all text bubbles means the latest turn isn't supported text."""
    h,w = pixels.shape[:2]
    scale = w/point_width
    y0,y1 = int(region.top*h),int(region.bottom*h)
    left,right = int(region.left*w),int(region.right*w)
    positions = []
    for a,b in ((left+int(22*scale),left+int(54*scale)),
                (right-int(54*scale),right-int(22*scale))):
        rgb = pixels[y0:y1,a:b,:3].astype(np.int16)
        if not rgb.size:
            continue
        ink = ((np.ptp(rgb,axis=2)>20) | (rgb.mean(axis=2)<165)).mean(axis=1) > .3
        edges = np.flatnonzero(np.diff(np.r_[False,ink,False]))
        for start,end in zip(edges[::2],edges[1::2]):
            if end-start >= 15*scale:
                positions.append((y0+start)/h)
    return max(positions,default=None)
