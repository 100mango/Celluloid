"""Pure mature Mach-O parser, copied unchanged from reviewed iOS package proof."""
import struct
import json
import plistlib
import re
MACH_MAGICS = (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")

def require(ok, message):
    if not ok:
        raise ValueError(message)

def version(number):
    return [number >> 16, (number >> 8) & 255, number & 255]

def mach_info(raw):
    """Read bounded 64-bit thin/fat headers and load commands, never execute."""
    require(len(raw) >= 32, 'Truncated Mach-O')
    magic = raw[:4]
    if magic in MACH_MAGICS[2:]:
        count = struct.unpack_from('>I', raw, 4)[0]
        width = 32 if magic == MACH_MAGICS[3] else 20
        require(0 < count <= 8 and 8 + width * count <= len(raw), 'Invalid fat architecture table')
        result, intervals, cpus = [], [], set()
        for i in range(count):
            pos = 8 + i * width
            cpu, subtype = struct.unpack_from('>II', raw, pos)
            if width == 32:
                offset, size, align, reserved = struct.unpack_from('>QQII', raw, pos + 8)
                require(reserved == 0, 'Invalid fat reserved value')
            else:
                offset, size, align = struct.unpack_from('>III', raw, pos + 8)
            require(cpu not in cpus and align <= 30 and offset % (1 << align) == 0,
                    'Duplicate or misaligned fat slice')
            require(offset >= 8 + width * count and size >= 32 and offset + size <= len(raw), 'Invalid fat slice bounds')
            require(all(offset + size <= a or offset >= b for a, b in intervals), 'Overlapping fat slices')
            require(raw[offset:offset + 4] in MACH_MAGICS[:2], 'Nested or unsupported Mach-O slice')
            slices = mach_info(raw[offset:offset + size])
            require(len(slices) == 1 and slices[0]['cpu'] == cpu and slices[0]['subtype'] == subtype, 'Fat slice identity mismatch')
            cpus.add(cpu); intervals.append((offset, offset + size)); result.extend(slices)
        return result
    require(magic in MACH_MAGICS[:2], 'Expected a 64-bit Mach-O product')
    endian = '<' if magic == MACH_MAGICS[0] else '>'
    _, cpu, subtype, kind, count, size, _, reserved = struct.unpack_from(endian + '8I', raw)
    require(reserved == 0 and kind in (2, 6, 8), 'Unsupported Mach-O type')
    require(0 < count <= 4096 and 32 + size <= len(raw), 'Invalid Mach-O command bounds')
    position, builds, links = 32, [], []
    for _ in range(count):
        require(position + 8 <= 32 + size, 'Truncated load command')
        command, length = struct.unpack_from(endian + 'II', raw, position)
        require(length >= 8 and length % 8 == 0 and position + length <= 32 + size, 'Invalid load command size')
        if command == 0x32:  # LC_BUILD_VERSION
            require(length >= 24, 'Short build version')
            platform, minimum, sdk, tools = struct.unpack_from(endian + '4I', raw, position + 8)
            require(length == 24 + tools * 8, 'Malformed build tool table')
            builds.append({'platform': platform, 'minimum': version(minimum), 'sdk': version(sdk)})
        if command in (0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023):
            require(length >= 24, 'Short dylib command')
            offset = struct.unpack_from(endian + 'I', raw, position + 8)[0]
            require(24 <= offset < length, 'Invalid dylib name offset')
            name = raw[position + offset:position + length]
            require(b'\0' in name, 'Unterminated dylib path')
            links.append(name.split(b'\0', 1)[0].decode('utf-8'))
        position += length
    require(position == 32 + size and len(builds) == 1, 'Missing, duplicate or inconsistent build version')
    return [{'cpu': cpu, 'subtype': subtype, 'kind': kind, **builds[0], 'libraries': links}]


def strings_dictionary(raw):
    """Accept compiled binary/XML plists or the checked-in quoted strings grammar."""
    try:
        value = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ValueError, TypeError):
        text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        token = re.compile(r'\s*(?:(?://[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)|("(?:[^"\\]|\\.)*")\s*=\s*("(?:[^"\\]|\\.)*")\s*;)')
        value, offset = {}, 0
        while text[offset:].strip():
            match = token.match(text, offset)
            require(match is not None, 'Malformed localization strings')
            offset = match.end()
            if match.group(1) is not None:
                key, item = json.loads(match.group(1)), json.loads(match.group(2))
                require(key not in value, 'Duplicate localization key')
                value[key] = item
    require(isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()),
            'Localization must be a string dictionary')
    return value
