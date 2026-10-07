"""Bounded readback of fixed owned Photos lifecycle PNGs; no process/file discovery."""
import hashlib,os,stat,struct,zlib

PNG_LIMIT=128*1024
ICC_LIMIT=4096
TEXT_LIMIT=16384
ORIGINAL_DIAGNOSTIC="lifecycle-original-observed.png"
DIMENSIONS=(1200,800)
NAMES=('lifecycle-source.png','lifecycle-expected-save.png','lifecycle-saved.png','lifecycle-cancelled.png','lifecycle-reverted.png')
PNG_UINT31_MAX=(1<<31)-1
SRGB_GAMMA=45455
SRGB_CHROMATICITIES=(31270,32900,64000,33000,30000,60000,15000,6000)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()

def inflate(data,maximum):
    decoder=zlib.decompressobj()
    try:output=decoder.decompress(data,maximum+1)
    except zlib.error as error:raise ValueError('Malformed compressed image/profile') from error
    require(len(output)<=maximum and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,'Truncated, trailing or oversized compressed image/profile')
    return output

def checked_icc(data):
    require(type(data) is bytes and 128<=len(data)<=ICC_LIMIT,'Invalid reference sRGB profile size')
    require(int.from_bytes(data[:4],'big')==len(data) and data[36:40]==b'acsp' and data[16:20]==b'RGB ' and data[20:24]==b'XYZ ','Invalid reference RGB ICC header')
    return data

def orientation(data):
    require(8<=len(data)<=16384 and data[:2] in (b'II',b'MM'),'Malformed PNG EXIF')
    order='little' if data[:2]==b'II' else 'big'
    number=lambda raw:int.from_bytes(raw,order)
    require(number(data[2:4])==42,'Wrong PNG EXIF TIFF magic')
    offset=number(data[4:8]);require(8<=offset<=len(data)-2,'Invalid PNG EXIF directory')
    count=number(data[offset:offset+2]);require(count<=64 and offset+2+count*12+4<=len(data),'Oversized/truncated PNG EXIF directory')
    found=[]
    for i in range(count):
        entry=data[offset+2+i*12:offset+14+i*12]
        if number(entry[:2])==274:
            require(number(entry[2:4])==3 and number(entry[4:8])==1,'Malformed PNG orientation type')
            found.append(number(entry[8:10]))
    require(len(found)<=1 and (not found or found==[1]),'Rotated/duplicate PNG orientation')
    require(number(data[offset+2+count*12:offset+6+count*12])==0,'Unexpected extra PNG image directory')
    return 1

def international_text(body):
    """Bounded PNG iTXt envelope only. No XML/XMP or textual semantics."""
    require(type(body) is bytes and len(body)<=TEXT_LIMIT,'Oversized iTXt envelope')
    keyword,separator,rest=body.partition(b'\0')
    require(separator and 1<=len(keyword)<=79 and all(32<=x<=126 or 161<=x<=255 for x in keyword)
            and not keyword.startswith(b' ') and not keyword.endswith(b' ') and b'  ' not in keyword,'Malformed iTXt keyword')
    require(len(rest)>=4 and rest[0] in (0,1) and (rest[0]==0 or rest[1]==0),'Malformed iTXt compression')
    language,separator,remaining=rest[2:].partition(b'\0');require(separator,'Missing iTXt language separator')
    require(all(45==x or 48<=x<=57 or 65<=x<=90 or 97<=x<=122 for x in language),'Malformed iTXt language bytes')
    translated,separator,text=remaining.partition(b'\0');require(separator,'Missing iTXt translated-keyword separator')
    if rest[0]:text=inflate(text,TEXT_LIMIT)
    require(len(text)<=TEXT_LIMIT and b'\0' not in text,'Oversized/null iTXt text')
    try:translated.decode('utf8');text.decode('utf8')
    except UnicodeDecodeError as error:raise ValueError('Malformed iTXt UTF-8') from error


def calibrated_chromaticities(values):
    """Admit a bounded, nondegenerate RGB calibration; do not convert samples.

    PNG cHRM uses unsigned 31-bit coordinates scaled by 100000, in white,
    red, green, blue order (https://www.w3.org/TR/png-3/#11cHRM). This
    supported subset requires physical xy coordinates and positive primary
    weights for the white point. Integer areas avoid rounding decisions.
    """
    require(type(values) is list and len(values)==8 and
            all(type(v) is int and 0<=v<=PNG_UINT31_MAX for v in values),'Invalid calibrated PNG chromaticity integers')
    points=list(zip(values[0::2],values[1::2]));white,red,green,blue=points
    require(all(x>=0 and y>0 and x+y<=100000 for x,y in points) and
            white[0]>0 and sum(white)<100000,'Unsupported calibrated PNG chromaticities')
    def area(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    determinant=area(red,green,blue)
    weights=(area(white,green,blue),area(red,white,blue),area(red,green,white))
    require(determinant!=0 and all(value*determinant>0 for value in weights),'Degenerate calibrated RGB primaries/white point')
    return values


def decode(data,reference_icc=None,dimensions=DIMENSIONS,*,calibrated_rgb=False):
    """Return stored samples, which are canonical sRGB only for strict profiles."""
    require(type(calibrated_rgb) is bool,'Invalid calibrated RGB switch')
    require(type(data) is bytes and 0<len(data)<=PNG_LIMIT and data.startswith(b'\x89PNG\r\n\x1a\n'),'Missing, oversized or wrong PNG')
    if reference_icc is not None:
        require(type(reference_icc) is dict and set(reference_icc)=={'bytes','sha256'} and type(reference_icc['bytes']) is int and 128<=reference_icc['bytes']<=ICC_LIMIT and type(reference_icc['sha256']) is str and len(reference_icc['sha256'])==64 and all(c in '0123456789abcdef' for c in reference_icc['sha256']),'Invalid independent ICC reference')
    index=8;chunks=[];seen=set();compressed=[];idat_ended=False;profile=None;profile_hash=None;intent=None;header=None
    gamma=None;chromaticities=None
    while index<len(data):
        require(index+12<=len(data) and len(chunks)<128,'Truncated/too many PNG chunks')
        length=int.from_bytes(data[index:index+4],'big');kind=data[index+4:index+8];end=index+12+length
        require(end<=len(data) and len(kind)==4 and all(65<=c<=90 or 97<=c<=122 for c in kind) and 65<=kind[2]<=90,'Malformed PNG chunk')
        body=data[index+8:index+8+length];crc=int.from_bytes(data[index+8+length:end],'big')
        require(zlib.crc32(kind+body)&0xffffffff==crc,'PNG CRC mismatch')
        require(chunks or kind==b'IHDR','PNG header must be first')
        if kind!=b'IDAT':require(kind not in seen,'Duplicate PNG chunk')
        if compressed and kind!=b'IDAT':idat_ended=True
        if kind==b'IHDR':
            require(not chunks and length==13,'Invalid PNG header')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',body)
            require((width,height)==tuple(dimensions) and 0<width<=1200 and 0<height<=800,'Wrong PNG dimensions')
            require(depth==8 and color in (2,6) and compression==filtering==interlace==0,'Unsupported PNG format/depth/interlace')
            header=(width,height,3 if color==2 else 4)
        elif kind==b'IDAT':
            require(not idat_ended and header is not None,'Noncontiguous PNG image data')
            compressed.append(body)
        elif kind==b'IEND':
            require(length==0 and compressed and end==len(data),'Malformed/trailing PNG end')
        elif kind==b'sRGB':
            require(not compressed and profile is None and length==1 and body[0]==0,'Invalid/contradictory sRGB profile')
            profile='sRGB';profile_hash=sha(body);intent=body[0]
        elif kind==b'iCCP':
            require(not compressed and profile is None and reference_icc is not None,'Unknown/contradictory ICC profile')
            split=body.find(b'\0');require(1<=split<=79 and split+2<len(body) and body[split+1]==0,'Malformed PNG ICC envelope')
            actual=checked_icc(inflate(body[split+2:],ICC_LIMIT));require(len(actual)==reference_icc['bytes'] and sha(actual)==reference_icc['sha256'],'PNG ICC differs from independent sRGB reference')
            profile='exact-reference-sRGB-ICC';profile_hash=sha(actual)
        elif kind==b'gAMA':
            if calibrated_rgb:
                require(not compressed and length==4,'Malformed/out-of-order calibrated PNG gamma')
                gamma=int.from_bytes(body,'big')
                require(0<gamma<=PNG_UINT31_MAX,'Invalid calibrated PNG gamma integer')
            else:require(not compressed and body==struct.pack('>I',SRGB_GAMMA),'Non-sRGB gamma')
        elif kind==b'cHRM':
            if calibrated_rgb:
                require(not compressed and length==32,'Malformed/out-of-order calibrated PNG chromaticities')
                chromaticities=calibrated_chromaticities(list(struct.unpack('>8I',body)))
            else:require(not compressed and body==struct.pack('>8I',*SRGB_CHROMATICITIES),'Non-sRGB chromaticities')
        elif kind==b'iTXt':international_text(body)
        elif kind==b'eXIf':orientation(body)
        elif kind==b'pHYs':require(length==9 and body[-1] in (0,1),'Malformed PNG physical dimensions')
        else:
            # Never ignore alpha, animation, alternate profile or critical data.
            require(kind in (b'tEXt',b'zTXt',b'tIME') and length<=16384,'Unreviewed PNG chunk')
        chunks.append(kind);seen.add(kind);index=end
    if calibrated_rgb:
        if profile is None:
            require(gamma is not None and chromaticities is not None,'Incomplete calibrated RGB profile')
            profile='gAMA-cHRM'
        else:
            # A higher-precedence sRGB/ICC declaration keeps the old strict
            # rules. It never turns conflicting calibration into a fallback.
            require(gamma is None or gamma==SRGB_GAMMA,'Non-sRGB gamma')
            require(chromaticities is None or tuple(chromaticities)==SRGB_CHROMATICITIES,'Non-sRGB chromaticities')
    require(chunks[-1:]==[b'IEND'] and header is not None and profile is not None,'Incomplete/unprofiled PNG')
    width,height,channels=header;stride=width*channels
    filtered=inflate(b''.join(compressed),(stride+1)*height)
    require(len(filtered)==(stride+1)*height,'Wrong PNG scanline span')
    pixels=bytearray(stride*height);previous=bytearray(stride)
    for y in range(height):
        offset=y*(stride+1);method=filtered[offset];require(method<=4,'Unknown PNG row filter')
        row=bytearray(filtered[offset+1:offset+1+stride])
        if method:
            for x in range(stride):
                a=row[x-channels] if x>=channels else 0;b=previous[x];c=previous[x-channels] if x>=channels else 0
                if method==1:predict=a
                elif method==2:predict=b
                elif method==3:predict=(a+b)//2
                else:
                    p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c)
                    predict=a if pa<=pb and pa<=pc else b if pb<=pc else c
                row[x]=(row[x]+predict)&255
        pixels[y*stride:(y+1)*stride]=row;previous=row
    if channels==3:
        rgba=bytearray(width*height*4);rgba[0::4]=pixels[0::3];rgba[1::4]=pixels[1::3];rgba[2::4]=pixels[2::3];rgba[3::4]=b'\xff'*(width*height)
    else:rgba=pixels
    require(all(a==255 for a in rgba[3::4]),'Nonopaque stored PNG')
    rgba=bytes(rgba)
    result={'width':width,'height':height,'color_type':6 if channels==4 else 2,'profile':profile,'profile_sha256':profile_hash,'rendering_intent':intent,'alpha':'opaque','rgba':rgba,'rgba_sha256':sha(rgba),'png_sha256':sha(data),'bytes':len(data)}
    if profile=='gAMA-cHRM':result.update(gamma_scaled=gamma,chromaticities_scaled=chromaticities)
    return result

def compare(first,second):
    require((first['width'],first['height'])==(second['width'],second['height']),'Different image dimensions')
    a,b=first['rgba'],second['rgba'];require(len(a)==len(b),'Different pixel spans')
    if a==b:return {'maximum_channel_difference':0,'different_pixels':0}
    maximum=max((abs(x-y) for x,y in zip(a,b)),default=0)
    count=sum(a[i:i+4]!=b[i:i+4] for i in range(0,len(a),4))
    return {'maximum_channel_difference':maximum,'different_pixels':count}


def read_owned_png(path):
    """Caller supplies one fixed, exact-test attachment path; no reported path discovery."""
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=PNG_LIMIT,'Invalid/oversized owned lifecycle PNG')
        snapshot=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        parts=[];remaining=before.st_size
        while remaining:
            data=os.read(fd,min(65536,remaining));require(data,'Truncated lifecycle PNG read')
            parts.append(data);remaining-=len(data)
        require(snapshot(os.fstat(fd))==snapshot(before)==snapshot(os.stat(path,follow_symlinks=False)),'Lifecycle PNG changed during read')
        return b''.join(parts)
    finally:os.close(fd)
