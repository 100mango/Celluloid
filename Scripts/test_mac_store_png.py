"""Synthetic codec checks; no screenshots are created or altered for marketing."""
import struct
import unittest
from unittest.mock import patch
import zlib
import mac_store_png as p


def png(width=1280,height=800,*,rgba=True,color=(35,90,170),alpha=255,mode=0,profile=True):
    channels=4 if rgba else 3; pixel=bytes((*color,alpha) if rgba else color);previous=bytes(width*channels);rows=[]
    for y in range(height):
        row=pixel*width;encoded=bytearray(row)
        if mode==0:
            rows.append(b'\0'+row);previous=row;continue
        for x in range(len(row)):
            a=row[x-channels] if x>=channels else 0;b=previous[x];c=previous[x-channels] if x>=channels else 0
            if mode==1:q=a
            elif mode==2:q=b
            elif mode==3:q=(a+b)//2
            elif mode==4:
                z=a+b-c;pa,pb,pc=abs(z-a),abs(z-b),abs(z-c);q=a if pa<=pb and pa<=pc else b if pb<=pc else c
            else:q=0
            encoded[x]=(row[x]-q)&255
        rows.append(bytes([mode])+encoded);previous=row
    header=p.chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6 if rgba else 2,0,0,0))
    return p.SIGNATURE+header+(p.chunk(b'sRGB',b'\0') if profile else b'')+p.chunk(b'IDAT',zlib.compress(b''.join(rows),9))+p.chunk(b'IEND',b'')


class PNGTests(unittest.TestCase):
    def test_native_rgb_is_byte_identical(self):
        with patch.object(p,'SIZES',((4,3),)):
            raw=png(4,3,rgba=False);out,proof=p.store_copy(raw)
        self.assertEqual(out,raw);self.assertEqual(proof['transformation'],'none')
    def test_all_filters_preserve_rgb_and_color_profile(self):
        with patch.object(p,'SIZES',((4,3),)):
            for mode in range(5):
                with self.subTest(mode=mode):
                    original=png(4,3,mode=mode);out,proof=p.store_copy(original)
                    a,ca,_=p.decode(original);b,cb,color=p.decode(out)
                    self.assertEqual(a,b);self.assertEqual(color,2);self.assertIn((b'sRGB',b'\0'),ca);self.assertIn((b'sRGB',b'\0'),cb)
                    self.assertEqual(proof['transformation'],'remove-fully-opaque-alpha-only');self.assertFalse(proof['resized']);self.assertFalse(proof['cropped'])
    def test_transparent_pixel_is_rejected_without_background_fill(self):
        with patch.object(p,'SIZES',((4,3),)),self.assertRaisesRegex(ValueError,'transparent-pixels'):p.store_copy(png(4,3,alpha=254))
    def test_unaccepted_dimensions_rejected(self):
        with self.assertRaisesRegex(ValueError,'dimensions'):p.store_copy(png(4,3))
    def test_crc_corruption_rejected(self):
        raw=bytearray(png(4,3));raw[20]^=1
        with patch.object(p,'SIZES',((4,3),)),self.assertRaisesRegex(ValueError,'crc'):p.store_copy(bytes(raw))
    def test_truncation_and_trailing_bytes_rejected(self):
        raw=png(4,3)
        for invalid in [raw[:-1],raw+b'x']:
            with patch.object(p,'SIZES',((4,3),)),self.assertRaises(ValueError):p.store_copy(invalid)
    def test_animation_and_transparency_chunks_rejected(self):
        raw=png(4,3)
        for kind in [b'acTL',b'tRNS']:
            changed=raw[:-12]+p.chunk(kind,b'')+raw[-12:]
            with patch.object(p,'SIZES',((4,3),)),self.assertRaises(ValueError):p.store_copy(changed)
    def test_oversized_compressed_payload_cannot_expand_past_shape(self):
        raw=p.SIGNATURE+p.chunk(b'IHDR',struct.pack('>IIBBBBB',4,3,8,6,0,0,0))+p.chunk(b'IDAT',zlib.compress(b'\0'*100000))+p.chunk(b'IEND',b'')
        with patch.object(p,'SIZES',((4,3),)),self.assertRaisesRegex(ValueError,'inflate'):p.store_copy(raw)
    def test_unknown_critical_chunk_rejected(self):
        raw=png(4,3);raw=raw[:-12]+p.chunk(b'ABCD',b'x')+raw[-12:]
        with patch.object(p,'SIZES',((4,3),)),self.assertRaisesRegex(ValueError,'critical'):p.store_copy(raw)
    def test_original_deadline_interrupts_decode(self):
        def expired():raise ValueError('original deadline')
        with patch.object(p,'SIZES',((4,3),)),self.assertRaisesRegex(ValueError,'original deadline'):p.store_copy(png(4,3),tick=expired)
    def test_raw_byte_bound_is_enforced(self):
        with patch.object(p,'LIMIT',20),self.assertRaisesRegex(ValueError,'byte-limit'):p.store_copy(png(4,3))


if __name__=='__main__':unittest.main()
