"""Synthetic bounded PNG adversaries; these tests do not qualify Photos UI."""
import hashlib,struct,unittest,zlib
import mac_host_lifecycle_pixels as p

def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
def fake_icc():
    b=bytearray(128);b[:4]=(128).to_bytes(4,'big');b[16:20]=b'RGB ';b[20:24]=b'XYZ ';b[36:40]=b'acsp';return bytes(b)
def encode(width=3,height=2,color=6,pixels=None,method=0,profile=None,extra=()):
    channels=4 if color==6 else 3;stride=width*channels
    pixels=pixels or bytes([13,127,231,255] if channels==4 else [13,127,231])*width*height
    rows=[];previous=bytes(stride)
    for y in range(height):
        row=pixels[y*stride:(y+1)*stride];filtered=bytearray(row)
        for x in range(stride):
            a=row[x-channels] if x>=channels else 0;b=previous[x];c=previous[x-channels] if x>=channels else 0
            if method==0:predict=0
            elif method==1:predict=a
            elif method==2:predict=b
            elif method==3:predict=(a+b)//2
            else:
                v=a+b-c;pa,pb,pc=abs(v-a),abs(v-b),abs(v-c);predict=a if pa<=pb and pa<=pc else b if pb<=pc else c
            filtered[x]=(filtered[x]-predict)&255
        rows.append(bytes([method])+filtered);previous=row
    profile=chunk(b'sRGB',b'\0') if profile is None else profile
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,color,0,0,0))+profile+b''.join(extra)+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
def pieces(data):
    rows=[];i=8
    while i<len(data):
        n=int.from_bytes(data[i:i+4],'big');rows.append((data[i+4:i+8],data[i+8:i+8+n]));i+=12+n
    return rows
def rebuild(rows):return b'\x89PNG\r\n\x1a\n'+b''.join(chunk(k,v) for k,v in rows)

class LifecyclePixelsTests(unittest.TestCase):
    def decode(self,data,**kwargs):return p.decode(data,dimensions=(3,2),**kwargs)
    def test_all_png_filters_and_rgb_rgba_recompute_exact_pixels(self):
        rgba=bytes([0,3,17,255,255,129,21,255,7,251,241,255,41,17,2,255,88,77,66,255,250,220,200,255])
        for color in [2,6]:
            raw=rgba if color==6 else bytes(v for i,v in enumerate(rgba) if i%4!=3)
            for method in range(5):
                row=self.decode(encode(color=color,pixels=raw,method=method))
                self.assertEqual(row['rgba'],rgba);self.assertEqual(row['rgba_sha256'],hashlib.sha256(rgba).hexdigest())
    def test_exact_reference_icc_only_and_decompression_bound(self):
        icc=fake_icc();data=encode(profile=chunk(b'iCCP',b'owned sRGB\0\0'+zlib.compress(icc)))
        self.assertEqual(self.decode(data,reference_icc={'bytes':len(icc),'sha256':p.sha(icc)})['profile'],'exact-reference-sRGB-ICC')
        with self.assertRaisesRegex(ValueError,'Unknown/contradictory'):self.decode(data)
        changed=bytearray(icc);changed[80]=1
        with self.assertRaisesRegex(ValueError,'differs from independent'):self.decode(data,reference_icc={'bytes':len(changed),'sha256':p.sha(bytes(changed))})
        bomb=encode(profile=chunk(b'iCCP',b'owned sRGB\0\0'+zlib.compress(b'x'*(p.ICC_LIMIT+1))))
        with self.assertRaisesRegex(ValueError,'oversized'):self.decode(bomb,reference_icc={'bytes':len(icc),'sha256':p.sha(icc)})
    def test_missing_changed_unknown_or_contradictory_profiles_reject(self):
        variants=[b'',chunk(b'sRGB',b'\1'),chunk(b'sRGB',b'\4'),chunk(b'sRGB',b'\0')*2,
            chunk(b'sRGB',b'\0')+chunk(b'gAMA',struct.pack('>I',100000)),
            chunk(b'sRGB',b'\0')+chunk(b'cHRM',b'\0'*32),chunk(b'cICP',b'\1\1\0\1')]
        for profile in variants:
            with self.subTest(profile=profile),self.assertRaises(ValueError):self.decode(encode(profile=profile))
        with self.assertRaises(ValueError):self.decode(encode(profile=chunk(b'iCCP',b'name\0\1'+zlib.compress(fake_icc()))),reference_icc={'bytes':128,'sha256':p.sha(fake_icc())})
    def test_type_size_crc_truncated_trailing_and_duplicate_chunks_reject(self):
        good=encode();bad_crc=bytearray(good);bad_crc[-1]^=1
        for bad in [b'',str(good),b'x'*(p.PNG_LIMIT+1),good[:-1],good+b'extra',bytes(bad_crc),rebuild(pieces(good)+[(b'IEND',b'')]),rebuild([pieces(good)[0]]+pieces(good))]:
            with self.subTest(length=len(bad)),self.assertRaises(ValueError):self.decode(bad)
    def test_wrong_dimensions_depth_color_compression_interlace_and_transparency_reject(self):
        header=pieces(encode())[0][1]
        for position,value in [(0,4),(4,3),(8,16),(9,3),(10,1),(11,1),(12,1)]:
            changed=bytearray(header)
            if position in (0,4):changed[position:position+4]=value.to_bytes(4,'big')
            else:changed[position]=value
            rows=pieces(encode());rows[0]=(b'IHDR',bytes(changed))
            with self.subTest(position=position),self.assertRaises(ValueError):self.decode(rebuild(rows))
        bad=bytes([1,2,3,254])*6
        with self.assertRaisesRegex(ValueError,'Nonopaque'):self.decode(encode(pixels=bad))
        with self.assertRaises(ValueError):self.decode(encode(color=2,extra=[chunk(b'tRNS',b'\0'*6)]))
    def test_compressed_scanline_bomb_extra_stream_truncation_and_bad_filter_reject(self):
        rows=pieces(encode());index=next(i for i,(k,_) in enumerate(rows) if k==b'IDAT');raw=zlib.decompress(rows[index][1])
        for compressed in [zlib.compress(raw+b'x'),zlib.compress(raw[:-1]),zlib.compress(raw)+zlib.compress(b'extra'),zlib.compress(raw)[:-1],zlib.compress(b'\5'+raw[1:])]:
            changed=list(rows);changed[index]=(b'IDAT',compressed)
            with self.assertRaises(ValueError):self.decode(rebuild(changed))
    def test_image_data_must_be_contiguous_and_critical_animation_chunks_reject(self):
        rows=pieces(encode());compressed=rows[2][1]
        bad=rows[:2]+[(b'IDAT',compressed[:2]),(b'tEXt',b'x'),(b'IDAT',compressed[2:])]+rows[3:]
        with self.assertRaisesRegex(ValueError,'Noncontiguous'):self.decode(rebuild(bad))
        for kind in [b'PLTE',b'acTL',b'fcTL',b'fdAT',b'ABCD']:
            with self.assertRaises(ValueError):self.decode(encode(extra=[chunk(kind,b'x')]))
    def test_orientation_is_unmodified_and_exif_offsets_are_bounded(self):
        def exif(value=1):return b'MM\0*\0\0\0\x08'+b'\0\1'+struct.pack('>HHI',274,3,1)+struct.pack('>H',value)+b'\0\0'+b'\0'*4
        self.assertEqual(self.decode(encode(extra=[chunk(b'eXIf',exif())]))['alpha'],'opaque')
        for value in [0,2,3,6,8]:
            with self.assertRaisesRegex(ValueError,'Rotated'):self.decode(encode(extra=[chunk(b'eXIf',exif(value))]))
        for raw in [b'x',exif()[:12],b'II\x2a\0'+(100000).to_bytes(4,'little')]:
            with self.assertRaises(ValueError):self.decode(encode(extra=[chunk(b'eXIf',raw)]))
    def test_itxt_standard_envelopes_are_color_neutral_before_or_after_idat(self):
        neutral=self.decode(encode())
        for body in [b'Comment\0\0\0\0\0',b'XML:com.adobe.xmp\0\0\0\0\0<not-parsed/>',
                     b'Comment\0\0\x7fzh-Hans\0'+"注释".encode()+b'\0'+"文本".encode(),
                     b'Comment\0\1\0en\0Comment\0'+zlib.compress(b'opaque text')]:
            p.international_text(body)
            for rows in [pieces(encode())[:2]+[(b'iTXt',body)]+pieces(encode())[2:],pieces(encode())[:-1]+[(b'iTXt',body)]+pieces(encode())[-1:]]:
                self.assertEqual(self.decode(rebuild(rows)),neutral | {'png_sha256':p.sha(rebuild(rows)),'bytes':len(rebuild(rows))})
    def test_itxt_malformed_and_compressed_bombs_reject_without_color_fallback(self):
        prefix=b'Comment\0\0\0\0\0';compressed=b'Comment\0\1\0\0\0'
        bad=[b'',b'\0\0\0\0\0',b'x'*80+b'\0\0\0\0\0',b' a\0\0\0\0\0',b'a  b\0\0\0\0\0',
             b'Comment\0\2\0\0\0',b'Comment\0\1\1\0\0',b'Comment\0\0\0en',b'Comment\0\0\0en\0bad',
             b'Comment\0\0\0!\0\0text',prefix+b'\0',prefix+b'\xff',b'Comment\0\0\0\0\xff\0text',
             prefix+b'x'*p.TEXT_LIMIT,compressed+zlib.compress(b'x'*(p.TEXT_LIMIT+1)),compressed+zlib.compress(b'ok')[:-1],
             compressed+zlib.compress(b'ok')+zlib.compress(b'extra')]
        for body in bad:
            with self.subTest(body=body[:30]),self.assertRaises(ValueError):self.decode(encode(extra=[chunk(b'iTXt',body)]))
        body=prefix+b'orientation=1;profile=sRGB'
        with self.assertRaisesRegex(ValueError,'Non-sRGB gamma'):self.decode(encode(extra=[chunk(b'iTXt',body),chunk(b'gAMA',struct.pack('>I',100000))]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.decode(encode(extra=[chunk(b'iTXt',body)]*2))
        raw=bytearray(encode(extra=[chunk(b'iTXt',body)]));raw[45]^=1
        with self.assertRaisesRegex(ValueError,'CRC'):self.decode(bytes(raw))
    def test_fixed_full_resolution_bound_and_comparison_mutations(self):
        full=encode(width=1200,height=800);row=p.decode(full);self.assertEqual(len(row['rgba']),1200*800*4)
        original=self.decode(encode());changed=bytearray(original['rgba']);changed[0]+=3
        modified=self.decode(encode(pixels=bytes(changed)))
        self.assertEqual(p.compare(original,original),{'maximum_channel_difference':0,'different_pixels':0})
        self.assertEqual(p.compare(original,modified),{'maximum_channel_difference':3,'different_pixels':1})

if __name__=='__main__':unittest.main()
