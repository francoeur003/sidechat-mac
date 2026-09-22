import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from auto_region import detect_region,AutoRegionError

def chat(width=900,height=800,left=300,right=None,bottom=620):
    right=width if right is None else right
    a=np.full((height,width,4),250,dtype=np.uint8)
    a[:,:left,:3]=228
    a[52:54,left:right,:3]=220
    a[bottom:bottom+2,left+10:right-10,:3]=220
    if right<width:
        a[:,right:,:3]=236
        a[:,right:right+2,:3]=210
    a[150:185,left+68:left+220,:3]=238
    a[300:338,right-240:right-60,:3]=[155,239,160]
    return a

class AutoRegionTests(unittest.TestCase):
    def assert_region(self,a,width,expected):
        r=detect_region(a,width)
        h,w=a.shape[:2]
        actual=(r.left*w,r.top*h,r.right*w,r.bottom*h)
        for x,y in zip(actual,expected):self.assertAlmostEqual(x,y,delta=6*a.shape[1]/width)
    def test_resize_recomputes_borders_and_composer(self):
        for w,h,l,b in [(900,800,300,620),(1100,700,420,490),(750,900,280,720)]:
            self.assert_region(chat(w,h,l,bottom=b),w,(l,55,w-4,b-3))
    def test_drawer_is_excluded(self):
        self.assert_region(chat(1145,833,416,778,674),1145,(416,55,778,671))
    def test_retina_and_single_scale_agree(self):
        a=chat();retina=np.repeat(np.repeat(a,2,axis=0),2,axis=1)
        r1,r2=detect_region(a,900),detect_region(retina,900)
        self.assertEqual(r1,r2)
    def test_image_rule_below_header_does_not_hide_chat(self):
        a=chat();a[63:65,320:885,:3]=50
        self.assert_region(a,900,(300,55,896,617))
    def test_empty_login_dark_and_nonchat_fail_closed(self):
        for a in [np.full((800,900,4),250,dtype=np.uint8),np.full((800,900,4),30,dtype=np.uint8),
                  np.random.default_rng(0).integers(0,255,(800,900,4),dtype=np.uint8)]:
            with self.assertRaises(AutoRegionError):detect_region(a,900)
    def test_busy_drawer_cannot_be_mistaken_for_composer(self):
        a=chat();a[640:720,330:870,:3]=[170,130,190]
        with self.assertRaises(AutoRegionError):detect_region(a,900)
    def test_two_plausible_chat_panes_fail_closed(self):
        a=chat(1200,800,240,650,620)
        a[:,680:,:3]=250;a[52:54,680:,:3]=220;a[620:622,690:1190,:3]=220
        with self.assertRaises(AutoRegionError):detect_region(a,1200)

if __name__=='__main__':unittest.main()
