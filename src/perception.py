"""Read a visible WeChat window through a calibrated region and native text bubbles.

Calibration stores geometry only. The sidebar and composer are physically excluded
before OCR; separate header observations identify the conversation. Pixel matching is
validated against the current light-mode Mac client, not a universal OCR guarantee.
"""

from __future__ import annotations

import re
import hashlib
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import Quartz
from chat_region import Region, load_region, image_pixels, bubble_boxes, latest_avatar_top

# --- layout constants (normalized 0..1 within the window; tuned on the probe data) ---
CHAT_PANE_X_MIN = 0.32
TITLE_BAR_Y_MAX = 0.90
INPUT_AREA_Y_MIN = 0.24
SIDEBAR_X_MAX = 0.30

# --- content filters ---
TIMESTAMP_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
UI_NOISE = (r"折叠聊天", r"共\s*\d+", r"搜索", r"发送", r"拖入文件", r"按住说话",
            r"语音输入文字", r"按住鼠标", r"按住 说话", r"输入文字",
            r"^[\w\-\u4e00-\u9fa5]{2,20}[:：].*\.\.\..*[）)]>$")  # folded-chat banner
MIN_CONF = 0.30
USERNAME_H_MAX = 0.026   # sender-name lines render smaller than bubble text
MESSAGE_H_MIN = 0.028
MIN_TEXT_LEN = 1


@dataclass
class TextBlock:
    text: str
    conf: float
    x: float
    y: float
    w: float
    h: float

    @property
    def x_right(self) -> float:
        return self.x + self.w

    @property
    def x_center(self) -> float:
        return self.x + self.w / 2


@dataclass
class Message:
    text: str
    side: str          # "them" | "me"
    y: float           # normalized, top-origin for readability
    conf: float
    h: float = 0.0
    sender: str | None = None
    lines: list[str] = field(default_factory=list)
    # normalized bounding box, kept spanning every folded line — the YOLO overlay draws
    # one box per message, so a 3-line message must cover all 3 lines, not its first
    x: float = 0.0
    w: float = 0.0
    last_y: float = 0.0     # top of the most recent folded line; fold bookkeeping only


@dataclass
class WindowInfo:
    wid: int
    pid: int
    title: str
    x: float
    y: float
    w: float
    h: float


# --------------------------------------------------------------------------- window


def screen_capture_ok() -> bool:
    """False when macOS has not granted Screen Recording to this app.

    Worth checking explicitly: without the grant macOS silently hides every window's
    title, so find_wechat_window() would just report "not found" and the user would see
    the panel disappear for no stated reason.
    """
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return True  # pre-10.15 has no such gate


def request_screen_capture() -> bool:
    """Ask the system to show the Screen Recording prompt (once per app identity)."""
    try:
        return bool(Quartz.CGRequestScreenCaptureAccess())
    except Exception:
        return False


def find_wechat_window(previous_wid: int | None = None) -> WindowInfo | None:
    """Largest titled WeChat window (the main one). Independent of window order."""
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    best: WindowInfo | None = None
    for w in wins:
        owner = w.get("kCGWindowOwnerName") or ""
        if "WeChat" not in owner and "微信" not in owner:
            continue
        if int(w.get("kCGWindowLayer") or 0) != 0:
            continue
        title = w.get("kCGWindowName") or ""
        b = dict(w.get("kCGWindowBounds") or {})
        wi = WindowInfo(
            wid=int(w.get("kCGWindowNumber") or 0),
            pid=int(w.get("kCGWindowOwnerPID") or 0),
            title=title,
            x=float(b.get("X", 0)), y=float(b.get("Y", 0)),
            w=float(b.get("Width", 0)), h=float(b.get("Height", 0)),
        )
        # main window: has a title, layer 0-ish, big, roughly window-shaped
        if not title or wi.w < 600 or wi.h < 400:
            continue
        # only a titled, window-sized window can be the main chat window
        if best is None or (wi.w * wi.h, wi.wid) > (best.w * best.h, best.wid):
            best = wi

    # stick with the window we already chose: WeChat 4.x keeps several equally-sized
    # windows around, and re-picking each tick let the target jump between them
    if previous_wid is not None and best is not None and best.wid != previous_wid:
        for w in wins:
            owner = w.get("kCGWindowOwnerName") or ""
            if "WeChat" not in owner and "微信" not in owner:
                continue
            if int(w.get("kCGWindowNumber") or 0) != previous_wid:
                continue
            title = w.get("kCGWindowName") or ""
            b = dict(w.get("kCGWindowBounds") or {})
            pw = float(b.get("Width", 0))
            ph = float(b.get("Height", 0))
            if title and pw >= 600 and ph >= 400:
                return WindowInfo(wid=previous_wid, pid=int(w.get("kCGWindowOwnerPID") or 0),
                                  title=title, x=float(b.get("X", 0)), y=float(b.get("Y", 0)),
                                  w=pw, h=ph)
    return best


def capture_window(wid: int, out: Path) -> bool:
    try:
        p = subprocess.run(["/usr/sbin/screencapture", "-x", "-o", "-l", str(wid), str(out)],
                           capture_output=True, text=True, timeout=3)
        return p.returncode == 0 and out.exists() and out.stat().st_size > 1000
    except subprocess.TimeoutExpired:
        return False


# ----------------------------------------------------------------------------- ocr


def _vision_blocks(handler, languages, chat_only: bool) -> list[TextBlock]:
    """Run one Vision text request against a handler that is already built.

    Shared by the file path and the in-memory path so the request settings — the part that
    was measured and tuned — exist exactly once.
    """
    import Vision
    from Quartz import CGRectMake

    blocks: list[TextBlock] = []

    def completion(request, error):
        if error:
            return
        for obs in request.results() or []:
            cands = obs.topCandidates_(1)
            if not cands:
                continue
            c = cands[0]
            bb = obs.boundingBox()
            blocks.append(TextBlock(
                text=c.string().strip(),
                conf=float(c.confidence()),
                x=float(bb.origin.x), y=float(bb.origin.y),
                w=float(bb.size.width), h=float(bb.size.height),
            ))

    req = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion)
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(list(languages))
    req.setUsesLanguageCorrection_(True)
    roi = None
    if chat_only:
        # Vision region of interest: normalized, origin BOTTOM-LEFT. Skipping the chat
        # list roughly halves OCR time. Note Vision then reports each observation's
        # bounding box RELATIVE TO THE ROI, so we convert back to full-window space.
        roi = (CHAT_PANE_X_MIN, INPUT_AREA_Y_MIN,
               1.0 - CHAT_PANE_X_MIN, 1.0 - INPUT_AREA_Y_MIN)
        req.setRegionOfInterest_(CGRectMake(*roi))
    handler.performRequests_error_([req], None)

    if roi is not None:
        rx, ry, rw, rh = roi
        for b in blocks:
            b.x = rx + b.x * rw
            b.y = ry + b.y * rh
            b.w *= rw
            b.h *= rh
    return blocks


def ocr(path: Path, languages=("zh-Hans",), chat_only: bool = True) -> list[TextBlock]:
    """Vision OCR over the chat pane, from a PNG on disk.

    zh-Hans alone: adding "en-US" bought nothing and cost time — on one screenshot the two
    settings returned text identical *block for block* at 433 ms vs 303 ms, i.e. ~30% of the
    OCR budget for no change in output. The zh-Hans model reads the Latin words that turn up
    inside Chinese chat text (product names, URLs, "gpt"/"glm-4-fl") by itself.

    Language correction stays ON (it costs ~30 ms more): it is what repairs ordinary OCR
    slips such as 记亿力 for 记忆力, and one wrong character changes what the judge reads.

    This is the fallback path; read_conversation() prefers the in-memory one.
    """
    import Vision
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    return _vision_blocks(handler, languages, chat_only)


def capture_image(wid: int, nominal: bool = True):
    """The window's pixels as a CGImage, without leaving the process. None when refused.

    Against `screencapture -l <wid>` writing a PNG, this is 4–29 ms versus 128–270 ms for the
    same window with identical recognition results (10 blocks, same text) — the difference
    being a subprocess spawn plus PNG encoding plus reading it back off disk. The capture
    runs every second, so when it works the saving is continuous.

    nominal=True captures at 1x instead of the default retina 2x: Vision's cost scales
    with pixel count, and chat text at 1x is still ~15 px tall — measured on rendered
    Chinese lines, recognition is identical block-for-block while OCR time roughly halves.
    The layout constants are all normalized, so nothing downstream notices the resolution.
    If a macOS update ever refuses the flag and returns NULL, read_conversation() falls
    back to the subprocess route and the log says so — degraded to the old behaviour,
    never broken.

    It does NOT always work: the same call returns NULL once the display is asleep, while
    `screencapture` keeps producing images. So callers must treat None as "use the slow
    route" rather than an error — read_conversation() does exactly that, and reports which
    route it took so a permanent fallback is visible instead of just feeling slow.
    """
    import Quartz
    try:
        opts = Quartz.kCGWindowImageBoundsIgnoreFraming
        if nominal:
            opts |= Quartz.kCGWindowImageNominalResolution
        return Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow, wid, opts)
    except Exception:
        return None


def ocr_image(image, languages=("zh-Hans",), chat_only: bool = True) -> list[TextBlock]:
    """Same request as ocr(), fed a CGImage directly — no PNG encode, no temp file."""
    import Vision
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    return _vision_blocks(handler, languages, chat_only)


def warm_ocr() -> float:
    """Pay Vision's one-off recognition-model load on a blank canvas, not a real read.

    The first text recognition in a process costs ~2x steady state (~0.7 s vs ~250 ms)
    while Vision loads its recognition model. Running that first request on a small white
    image needs no WeChat window at all — it works even when WeChat starts after this
    app — so the read loop's first real read finds the framework already paid for.
    Returns the elapsed milliseconds, or -1.0 when the request itself failed.
    """
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(
        None, 64, 64, 8, 64 * 4, cs, Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1.0, 1.0, 1.0, 1.0)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, 64, 64))
    image = Quartz.CGBitmapContextCreateImage(ctx)
    t0 = time.perf_counter()
    try:
        ocr_image(image, chat_only=False)
    except Exception:
        return -1.0
    return (time.perf_counter() - t0) * 1000


# ----------------------------------------------------------------- fingerprint

# Fixed grid, independent of window size: a resize re-fingerprints as "different" instead
# of aliasing onto a match. At 128x224 a single chat character still covers a handful of
# cells, so the smallest change anyone could send shifts far more bytes than noise.
_FP_W, _FP_H = 128, 224


def _fingerprint(image, region=None, window_id=0) -> bytes | None:
    """The chat pane (title band down to just above the input box) as a small grayscale
    thumbnail; None when anything in the pipeline refuses.

    read_conversation() compares this between ticks: the same picture means the pixels
    did not move, so OCR cannot have anything new to report and its ~300 ms can be
    skipped. The input box is excluded on purpose — the caret blinks there, and it would
    keep a quiet screen looking busy forever. The chat list is excluded for the same
    reason (unread badges), which is also why the crop starts at CHAT_PANE_X_MIN.
    """
    import ctypes

    try:
        w = Quartz.CGImageGetWidth(image)
        h = Quartz.CGImageGetHeight(image)
        # Layout constants here are bottom-origin (Vision's convention); CGImage cropping
        # is top-origin, so the band "input-area top edge .. window top" becomes
        # y=0 .. (1 - INPUT_AREA_Y_MIN) from the top.
        region = region or Region(CHAT_PANE_X_MIN, .10, 1, 1-INPUT_AREA_Y_MIN)
        crop = Quartz.CGImageCreateWithImageInRect(
            image,
            Quartz.CGRectMake(int(region.left*w), 0,
                              int((region.right-region.left)*w), int(region.bottom*h)))
        cs = Quartz.CGColorSpaceCreateDeviceGray()
        buf = ctypes.create_string_buffer(_FP_W * _FP_H)
        ctx = Quartz.CGBitmapContextCreate(
            buf, _FP_W, _FP_H, 8, _FP_W, cs, Quartz.kCGImageAlphaNone)
        Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, _FP_W, _FP_H), crop)
        identity = hashlib.sha256(repr((window_id,w,h,region)).encode()).digest()
        return identity + buf.raw
    except Exception:
        return None


def _same_frame(a: bytes | None, b: bytes | None) -> bool:
    """True when two fingerprints are the same picture.

    Exact equality covers the static case at C speed. When it fails, a tolerant count
    decides: a few small byte deltas is rendering noise (treat as same, skip OCR),
    anything a person sent rewrites whole glyph cells (treat as changed). Missing a real
    change would mean missing a message, so the threshold sits well under what one
    character produces.
    """
    if a is None or b is None:
        return False
    if len(a) != len(b) or a[:32] != b[:32]:
        return False
    if a == b:
        return True
    return sum(1 for x, y in zip(a[32:], b[32:]) if abs(x - y) >= 8) < 6


# ---------------------------------------------------------------------- extraction


def _is_noise(b: TextBlock) -> bool:
    if b.conf < MIN_CONF or len(b.text) < MIN_TEXT_LEN:
        return True
    if TIMESTAMP_RE.match(b.text):
        return True
    return any(re.search(pat, b.text) for pat in UI_NOISE)


def extract_chat_title(blocks: list[TextBlock], region=None) -> str:
    region = region or Region(CHAT_PANE_X_MIN, .10, 1, .76)
    cands = [b for b in blocks if b.x >= region.left and b.x_right <= region.right
             and 0 <= 1-b.y-b.h < region.top and b.conf >= .3
             and len(b.text) >= 2 and not _is_noise(b)]
    if not cands:
        return ""
    # Vision may split a title around an emoji/group number. Keep its adjacent pieces,
    # otherwise groups "JARVIS 5" and "JARVIS 7" collapse onto the same identity.
    cands = [b for b in cands if re.search(r"[\w\u4e00-\u9fff]",b.text)]
    if not cands:
        return ""
    top = min(1-b.y-b.h for b in cands)
    band = sorted([b for b in cands if abs(1-b.y-b.h-top)<.022],key=lambda b:b.x)
    keep = [band[0]]
    for b in band[1:]:
        if b.x-keep[-1].x_right > .04:
            break
        keep.append(b)
    return " ".join(b.text for b in keep)


def extract_messages(blocks: list[TextBlock], max_messages: int = 12,
                     *, region=None, bubbles=None) -> list[Message]:
    """Read only text contained in a native bubble, never mutate Vision observations.

    Bubble boundaries keep wrapped lines together and separate adjacent senders.
    Font height is not a speaker/name classifier: native text varies with window size.
    """
    if bubbles is None:
        return []  # no unbounded text-only fallback
    region = region or Region(CHAT_PANE_X_MIN, .10, 1, .76)
    messages = []
    for side,x0,y0,x1,y1 in bubbles:
        inside = [b for b in blocks if b.conf >= MIN_CONF and b.text
                  and x0 <= b.x_center <= x1 and y0 <= 1-b.y-b.h/2 <= y1
                  and b.x >= x0-.003 and b.x_right <= x1+.003]
        if not inside:
            continue
        inside.sort(key=lambda b: (round((1-b.y-b.h)/.008),b.x))
        lines = []
        for b in inside:
            top = 1-b.y-b.h
            if lines and abs(top-lines[-1][0]) < min(b.h*.5,.010):
                lines[-1][1].append(b)
            else:
                lines.append([top,[b]])
        texts = [" ".join(b.text for b in sorted(row,key=lambda b:b.x)) for _,row in lines]
        # A sender may sit immediately above the bubble; it is metadata, never content.
        names = [b for b in blocks if side == "them" and b.conf >= .3
                 and abs(b.x-x0) < .02 and 0 < y0-(1-b.y) < .035
                 and len(b.text) <= 40 and not _is_noise(b)
                 and not any(a <= b.x_center <= c and d <= 1-b.y-b.h/2 <= e
                             for _,a,d,c,e in bubbles)]
        sender = min(names,key=lambda b:y0-(1-b.y)).text if names else None
        messages.append(Message(text="\n".join(texts), side=side, y=y0,
                                conf=min(b.conf for b in inside),h=y1-y0,sender=sender,
                                lines=texts,x=x0,w=x1-x0,last_y=lines[-1][0]))
    return sorted(messages,key=lambda m:m.y)[-max_messages:]


def looks_like_sender_name(msg: Message, following: Message | None) -> bool:
    """Heuristic: group chats render the sender name as a short line above the bubble."""
    if following is None:
        return False
    t = msg.text.strip()
    if len(t) > 16 or "\n" in t:
        return False
    gap = following.y - msg.y
    return gap > 0.045


# ---------------------------------------------------------------------- public API


def _ocr_region(image, region):
    """Physically crop first. The OCR engine never receives the sidebar or composer."""
    w,h = Quartz.CGImageGetWidth(image),Quartz.CGImageGetHeight(image)
    left,right,bottom = int(region.left*w),int(region.right*w),int(region.bottom*h)
    crop = Quartz.CGImageCreateWithImageInRect(image,Quartz.CGRectMake(left,0,right-left,bottom))
    blocks = ocr_image(crop,chat_only=False)
    for b in blocks:
        b.x = (left+b.x*(right-left))/w
        b.w *= (right-left)/w
        b.y = 1-bottom/h+b.y*bottom/h
        b.h *= bottom/h
    return blocks


def read_conversation(max_messages: int = 12, previous_wid: int | None = None,
                      prev_fingerprint: bytes | None = None) -> dict:
    """Bounded capture -> calibrated crop -> bubble text. Temporary pixels stay local."""
    from Foundation import NSURL
    t0 = time.perf_counter()
    win = find_wechat_window(previous_wid)
    if win is None:
        return {"ok":False,"error":"未找到可见的微信聊天窗口","messages":[]}
    window = {"wid":win.wid,"title":win.title,"w":win.w,"h":win.h,"x":win.x,"y":win.y}
    try:
        region = load_region(win.w,win.h)
    except ValueError as exc:
        return {"ok":False,"error":str(exc),"messages":[],"window":window}
    # The deprecated CGWindowListCreateImage can block for minutes on this macOS.
    # The official subprocess fallback is bounded and reliably captures current pixels.
    with tempfile.TemporaryDirectory(prefix="jev-capture-") as td:
        path = Path(td)/"window.png"
        if not capture_window(win.wid,path):
            return {"ok":False,"error":"无法读取微信窗口，请检查屏幕录制权限","messages":[],"window":window}
        source = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(path)),None)
        image = Quartz.CGImageSourceCreateImageAtIndex(source,0,None)
    if image is None:
        return {"ok":False,"error":"截图为空，请重新打开微信","messages":[],"window":window}
    fingerprint = _fingerprint(image,region,win.wid)
    t_cap = time.perf_counter()
    base = dict(window=window,region=region.as_dict(),fingerprint=fingerprint)
    if _same_frame(fingerprint,prev_fingerprint):
        return dict(base,ok=True,unchanged=True,messages=[],chat_title="",n_blocks=0,
                    timing_ms=dict(capture=(t_cap-t0)*1000,ocr=0.,total=(t_cap-t0)*1000,capture_path="subprocess"))
    blocks = _ocr_region(image,region)
    pixels = image_pixels(image)
    bubbles = bubble_boxes(pixels,region,win.w)
    # A group-details drawer overlays the calibrated chat. Never turn its controls into chat.
    controls = {b.text for b in blocks if any(label in b.text for label in
                ("群聊名称","消息免打扰","保存到通讯录","群公告","搜索群成员"))
                and not any(x0 <= b.x_center <= x1 and y0 <= 1-b.y-b.h/2 <= y1
                            for _,x0,y0,x1,y1 in bubbles)}
    if len(controls) >= 2:
        return dict(base,ok=False,error="请先关闭微信右侧群资料面板",messages=[])
    title = extract_chat_title(blocks,region)
    msgs = extract_messages(blocks,max_messages,region=region,bubbles=bubbles)
    avatar_top = latest_avatar_top(pixels,region,win.w)
    if msgs and avatar_top is not None and avatar_top > msgs[-1].y+msgs[-1].h:
        return dict(base,ok=False,error="最新一条未识别为文字，请等待文字消息或滚动到底部",messages=[])
    t_ocr = time.perf_counter()
    return dict(base,ok=True,unchanged=False,chat_title=title,messages=msgs,
                context_id=(win.wid,re.sub(r"[（(]\d+[）)]$","",re.sub(r"\s+","",title)).casefold(),
                            tuple(region.as_dict().values())),
                timing_ms=dict(capture=(t_cap-t0)*1000,ocr=(t_ocr-t_cap)*1000,
                               total=(t_ocr-t0)*1000,capture_path="subprocess"),
                n_blocks=len(blocks))


if __name__ == "__main__":
    import json

    res = read_conversation()
    if not res["ok"]:
        print("ERROR:", res["error"])
        raise SystemExit(1)
    print(f"window {res['window']['w']:.0f}x{res['window']['h']} "
          f"capture={res['timing_ms']['capture']:.0f}ms ocr={res['timing_ms']['ocr']:.0f}ms "
          f"blocks={res['n_blocks']}")
    print("--- messages (top to bottom) ---")
    for m in res["messages"]:
        print(f"  [{m.side:4s}] y={m.y:.3f} conf={m.conf:.2f} | {m.text}")
