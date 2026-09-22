import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from chat_region import Region, bubble_boxes, load_region, latest_avatar_top
from perception import TextBlock, extract_messages, extract_chat_title, _same_frame


def block(text, x, top, width=.08, height=.016):
    return TextBlock(text, 1., x, 1-top-height, width, height)


class RegionTests(unittest.TestCase):
    def test_calibration_survives_move_but_rejects_resize(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"region.json"
            p.write_text(json.dumps(dict(width=829,height=840,left=.507,top=.063,right=.994,bottom=.809)))
            self.assertEqual(load_region(829,840,p).left,.507)
            with self.assertRaisesRegex(ValueError,"尺寸"):
                load_region(1000,840,p)
            data = json.loads(p.read_text()); data['right'] = float('nan');p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_region(829,840,p)

    def test_native_short_messages_and_multiline_not_names(self):
        region = Region(.5,.06,1,.82)
        blocks = [block('测试群',.54,.02),block('侧栏错误消息',.2,.40),
                  block('发送者',.60,.15),block('第一行',.60,.20),
                  block('第二行',.60,.225),block('第三行',.60,.25),
                  block('10:00',.72,.29),block('好',.60,.35),
                  block('收到',.84,.43),block('未发送草稿',.60,.90)]
        saved_y = [b.y for b in blocks]
        bubbles = [('them',.59,.19,.8,.28),('them',.59,.34,.7,.38),('me',.83,.42,.94,.46)]
        msgs=extract_messages(blocks,region=region,bubbles=bubbles)
        self.assertEqual([m.text for m in msgs],['第一行\n第二行\n第三行','好','收到'])
        self.assertEqual([m.side for m in msgs],['them','them','me'])
        self.assertEqual(saved_y,[b.y for b in blocks])
        self.assertEqual(extract_chat_title(blocks,region),'测试群')

    def test_bubble_geometry_ignores_sidebar_and_composer(self):
        pixels=np.full((840,829,4),250,dtype=np.uint8)
        pixels[200:240,480:620,:3]=[238,238,240]
        pixels[310:350,650:760,:3]=[157,242,159]
        pixels[500:540,100:300,:3]=[238,238,240]
        pixels[730:770,490:600,:3]=[238,238,240]
        boxes=bubble_boxes(pixels,Region(.507,.063,.994,.809),829)
        self.assertEqual([b[0] for b in boxes],['them','me'])

    def test_distinct_window_identity_never_matches(self):
        self.assertFalse(_same_frame(b'a'*32+b'\x00'*100,b'b'*32+b'\x00'*100))
        self.assertFalse(_same_frame(b'a'*32+b'\x00'*100,b'a'*32+b'\x00'*101))

    def test_split_group_title_keeps_group_number(self):
        blocks=[block('JARVIS',.53,.024,.11),block('7群 (31)',.65,.024,.09),block('••',.93,.024)]
        self.assertEqual(extract_chat_title(blocks,Region(.5,.063,.99,.81)),'JARVIS 7群 (31)')

    def test_latest_avatar_is_not_a_system_notice(self):
        pixels=np.full((840,829,4),250,dtype=np.uint8)
        region=Region(.507,.063,.994,.809)
        self.assertIsNone(latest_avatar_top(pixels,region,829))
        pixels[300:330,442:476,:3]=[90,40,150]
        pixels[460:490,774:806,:3]=[30,130,80]
        self.assertAlmostEqual(latest_avatar_top(pixels,region,829),460/840)


if __name__=='__main__':
    unittest.main()
