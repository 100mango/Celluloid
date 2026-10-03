#!/usr/bin/env python3
import struct, zlib
from pathlib import Path
width,height=640,480
raw=b''.join(b'\0'+b''.join(bytes((x*255//width,y*255//height,128)) for x in range(width)) for y in range(height))
def chunk(t,data):return struct.pack('>I',len(data))+t+data+struct.pack('>I',zlib.crc32(t+data)&0xffffffff)
Path('/tmp/celluloid-fixture.png').write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
