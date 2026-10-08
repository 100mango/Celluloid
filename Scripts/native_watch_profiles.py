"""Select exact observed SDK27 endpoint profiles, never substitute another size."""
PROFILES = [('baseline', 'Apple Watch Series 12 (46mm)'), ('small', 'Apple Watch SE 3 (40mm)'), ('large', 'Apple Watch Ultra 4 (49mm)')]

def select_profiles(runtime, device_types):
    supported = {entry['identifier'] for entry in runtime.get('supportedDeviceTypes', [])}
    if not supported:
        raise ValueError('Runtime did not report compatible Watch device types')
    result = []
    for key, name in PROFILES:
        matches = [item for item in device_types if item.get('name') == name and item['identifier'] in supported]
        if len(matches) != 1:
            raise ValueError(f'Required installed compatible Watch endpoint is absent or ambiguous: {name}')
        result.append((key, matches[0]))
    return result
