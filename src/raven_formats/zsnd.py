from collections import namedtuple
from struct import pack, unpack, calcsize
import json, wave, glob, math
from operator import itemgetter
from pathlib import Path
from importlib.resources import open_text
from argparse import ArgumentParser
from . import adpcm

Header = namedtuple('Header', [
    'size',
    'header_size',
    'sound_count',
    'sound_hashes_offset',
    'sounds_offset',
    'sample_count',
    'sample_hashes_offset',
    'samples_offset',
    'sample_file_count',
    'sample_file_hashes_offset',
    'sample_files_offset',
    'phrase_count',
    'phrase_hashes_offset',
    'phrases_offset',
    'track_def_count',
    'track_def_hashes_offset',
    'track_defs_offset',
    'reserved_count',
    'reserved_hashes_offset',
    'reserved_offset',
    'keymap_count',
    'keymap_hashes_offset',
    'keymaps_offset'
])

header_fmt = '< 23I'
header_big_fmt = '> 23I'
header_size = calcsize(header_fmt)

hash_fmt = '< 2I'
hash_big_fmt = '> 2I'
hash_size = calcsize(hash_fmt)

sound_fmt = '< 2H B x B 2x B x B 7x 3B 2x'
sound_big_fmt = '> 2H B x B 2x B x B 7x 3B 2x'
sound_size = calcsize(sound_fmt)

sample_pc_fmt = '< 2H I 16x'
sample_gamecube_fmt = '> 2H I 16x'
sample_xbox_fmt = '< 2H I 20x'
sample_xenon_fmt = '> 2H I 28x'
sample_pc_gamecube_size = calcsize(sample_pc_fmt)
sample_xbox_size = calcsize(sample_xbox_fmt)
sample_xenon_size = calcsize(sample_xenon_fmt)

sample_ps2_fmt = '< 3H 10x'
sample_ps3_fmt = '> 3H 10x'
sample_psx_size = calcsize(sample_ps2_fmt)

sample_file_pc_fmt = '< 3I 64s'
sample_file_xbox_fmt = '< 3I 8x 64s'
sample_file_xenon_fmt = '> 3I 8x 64s'
sample_file_pc_size = calcsize(sample_file_pc_fmt)
sample_file_xbox_size = calcsize(sample_file_xbox_fmt)

sample_file_ps2_fmt = '< 2I'
sample_file_ps3_fmt = '> 2I'
sample_file_psx_size = calcsize(sample_file_ps2_fmt)

sample_file_gamecube_fmt = '> 2I 4s'
sample_file_gamecube_size = calcsize(sample_file_gamecube_fmt)

zsnd_size_fmt = '< I'
zsnd_size_big_fmt = '> I'

vag_header_fmt = '> 4s I 4x 2I 12x 16s'
vag_header_size = calcsize(vag_header_fmt)

def is_big_endian(platform: str) -> bool:
    return platform == 'GCUB' or platform == 'PS3' or platform == 'XENO'

def get_header_format(platform: str) -> str:
    return header_big_fmt if (is_big_endian(platform)) else header_fmt

def get_hash_format(platform: str) -> str:
    return hash_big_fmt if (is_big_endian(platform)) else hash_fmt

def get_sound_format(platform: str) -> str:
    return sound_big_fmt if (is_big_endian(platform)) else sound_fmt

def get_sample_format(platform: str) -> str:
    sample_format = {
        'PC': sample_pc_fmt,
        'PS2': sample_ps2_fmt,
        'XBOX': sample_xbox_fmt,
        'GCUB': sample_gamecube_fmt,
        'PS3': sample_ps3_fmt,
        'XENO': sample_xenon_fmt
    }
    return sample_format.get(platform)

def get_sample_file_format(platform: str) -> str:
    sample_file_format = {
        'PC': sample_file_pc_fmt,
        'PS2': sample_file_ps2_fmt,
        'XBOX': sample_file_xbox_fmt,
        'GCUB': sample_file_gamecube_fmt,
        'PS3': sample_file_ps3_fmt,
        'XENO': sample_file_xenon_fmt
    }
    return sample_file_format.get(platform)

def get_sample_size(platform: str) -> int:
    if platform == 'PC' or platform == 'GCUB':
        return sample_pc_gamecube_size
    elif platform == 'PS2' or platform == 'PS3':
        return sample_psx_size
    elif platform == 'XBOX':
        return sample_xbox_size
    elif platform == 'XENO':
        return sample_xenon_size
    return -1

def get_sample_file_size(platform: str) -> int:
    if platform == 'PC':
        return sample_file_pc_size
    elif platform == 'GCUB':
        return sample_file_gamecube_size
    elif platform == 'PS2' or platform == 'PS3':
        return sample_file_psx_size
    elif platform == 'XBOX' or platform == 'XENO':
        return sample_file_xbox_size
    return -1

hash_strings = {}

def hash2str(sound_hash: int):
    global hash_strings

    key = str(sound_hash)

    if not hash_strings:
        with open_text('raven_formats.data', 'zsnd_hashes.json') as hashes_file:
            hash_strings = json.load(hashes_file)
    return hash_strings[key] if (key in hash_strings) else sound_hash
    
def pjw_hash(key: str) -> int:
    hash = 0
    test = 0
    for c in key:
        hash = (hash << 4) + ord(c)
        test = hash & 0xF0000000
        if test != 0:
            hash = ((hash ^ (test >> 24)) & (~0xF0000000))
    return (hash & 0x7FFFFFFF)

def pitch2rate(pitch: int) -> int:
    rate = pitch * 44100 / 4096
    return int(rate if rate.is_integer() else round(rate, -1))

def rate2pitch(rate: int) -> int:
    return round(rate * 4096 / 44100)

def multipleOf(n: int, x: int) -> int:
    return math.ceil(n / x) * x

def get_channels(sample_flags: int) -> int:
    channels = 1
            
    if sample_flags & 2 != 0:
        channels = 4 if (sample_flags & 32 != 0) else 2
    return channels

def read_zsnd(zsnd_path: Path, output_path: Path) -> dict:
    with zsnd_path.open(mode='rb') as zsnd_file:
        if (zsnd_file.read(4) != b'ZSND'):
            raise ValueError('Invalid magic number')

        platform = zsnd_file.read(4).decode('utf-8').rstrip()

        if platform != 'PC' and platform != 'PS2' and platform != 'XBOX' and platform != 'GCUB' and platform != 'PS3' and platform != 'XENO':
            raise ValueError(f'Platform {platform} is not supported')

        header = Header._make(unpack(get_header_format(platform), zsnd_file.read(header_size)))
        
        if header.sound_count <= 0 or header.sample_count <= 0 or header.sample_file_count <= 0:
            return
        
        data = {}
        sounds = []
        samples = []
        sound_hashes = []

        data['platform'] = platform
        data['sounds'] = sounds
        data['samples'] = samples

        zsnd_file.seek(header.sound_hashes_offset)

        for i in range(header.sound_count):
            sound_hashes.append(unpack(get_hash_format(platform), zsnd_file.read(hash_size)))

        sound_hashes.sort(key=itemgetter(1))
        zsnd_file.seek(header.sounds_offset)

        for hash_value, index in sound_hashes:
            sound = unpack(get_sound_format(platform), zsnd_file.read(sound_size))

            sounds.append({
                'hash': hash2str(hash_value),
                'sample_index': sound[0],
                'flags': sound[3]
            })

        for sample_index in range(header.sample_count):
            sample_size = get_sample_size(platform)
            zsnd_file.seek(header.samples_offset + sample_index * sample_size)
            sample = unpack(get_sample_format(platform), zsnd_file.read(sample_size))

            sample_file_size = get_sample_file_size(platform)
            zsnd_file.seek(header.sample_files_offset + sample[0] * sample_file_size)
            sample_file = unpack(get_sample_file_format(platform), zsnd_file.read(sample_file_size))

            if (platform == 'PC' or platform == 'XBOX' or platform == 'XENO'):
                sample_file_name = sample_file[3].decode('utf-8').rstrip('\u0000')
            else:
                suffix = '.dsp' if (platform == 'GCUB') else '.vag'
                sample_file_name = f'{sample_index}{suffix}'

            sample_file_path = output_path.parent / output_path.stem / sample_file_name
            sample_file_path.parent.mkdir(parents=True, exist_ok=True)
            sample_file_name = sample_file_path.stem
            
            counter = 1

            while sample_file_path.exists():
                sample_file_path = sample_file_path.with_stem(f'{sample_file_name}_{counter}')
                counter += 1

            is_psx = platform == 'PS2' or platform == 'PS3'

            sample_data = {
                'file': str(sample_file_path),
                'format': sample_file[2] if (platform == 'PC' or platform == 'XBOX' or platform == 'XENO') else -1,
                'sample_rate': pitch2rate(sample[1]) if (is_psx) else sample[2],
                'flags': sample[2] if (is_psx) else sample[1]
            }
    
            sample_flags = sample_data['flags']
            sample_file_format = sample_data['format']

            if (sample_flags <= 0): sample_data.pop('flags')
            if (sample_file_format < 0): sample_data.pop('format')

            samples.append(sample_data)

            zsnd_file.seek(sample_file[0])
            sample_file_size = sample_file[1]
            sample_rate = sample_data['sample_rate']
            channels = get_channels(sample_flags)
  
            with sample_file_path.open(mode='wb') as sample_file:
                if is_psx and channels == 1:
                    sample_file.write(pack(vag_header_fmt, b'VAGp', 0x20, sample_file_size, sample_rate, sample_file_path.stem.encode('utf-8')))

                sample_file_data = zsnd_file.read(sample_file_size)

                if platform == 'PC' and channels == 1:
                    with wave.open(sample_file, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(sample_rate)

                        if sample_file_format == 106:
                            wav_file.writeframes(adpcm.decode(sample_file_data))
                        else:
                            wav_file.writeframes(sample_file_data)
                else:
                    sample_file.write(sample_file_data)
        return data

def write_zsnd(data: dict, output_path: Path):
    with output_path.open(mode='wb') as zsnd_file:
        zsnd_name = output_path.stem.upper()
        platform = data['platform']
        hash_format = get_hash_format(platform)
        sound_format = get_sound_format(platform)
        sample_format = get_sample_format(platform)
        sample_file_format = get_sample_file_format(platform)
        is_psx = platform == 'PS2' or platform == 'PS3'

        json_sounds = data['sounds']
        json_samples = data['samples']
        sound_count = len(json_sounds)
        sample_count = len(json_samples)
        sound_hashes_offset = 8 + header_size
        sounds_offset = sound_hashes_offset + sound_count * hash_size
        sample_hashes_offset = sounds_offset + sound_count * sound_size
        samples_offset = sample_hashes_offset + sample_count * hash_size
        sample_file_hashes_offset = samples_offset + sample_count * get_sample_size(platform)
        sample_files_offset = sample_file_hashes_offset + sample_count * hash_size
        files_data_offset = sample_files_offset + sample_count * get_sample_file_size(platform)

        if platform != 'GCUB':
            files_data_offset += multipleOf(files_data_offset, 16) - files_data_offset

        zsnd_file.write(b'ZSND')
        zsnd_file.write(platform.ljust(4).encode('utf-8'))
        zsnd_file.write(pack(get_header_format(platform), 0, files_data_offset, 
            sound_count, sound_hashes_offset, sounds_offset, 
            sample_count, sample_hashes_offset, samples_offset, 
            sample_count, sample_file_hashes_offset, sample_files_offset, 
            0, files_data_offset, files_data_offset, 
            0, files_data_offset, files_data_offset, 
            0, files_data_offset, files_data_offset, 
            0, files_data_offset, files_data_offset))
        zsnd_file.write(pack(f'{files_data_offset - sound_hashes_offset}x'))

        sound_hashes = []
        sample_hashes = []
        sample_file_hashes = []

        zsnd_file.seek(sounds_offset)

        for sample_index, sound in enumerate(json_sounds):
            sound_hash = sound['hash']
            byte_11 = 15 if (is_psx) else 127
            byte_19_20_21 = 32 if (platform == 'PS3') else 0

            sound_hashes.append((pjw_hash(sound_hash.upper()) if (isinstance(sound_hash, str)) else sound_hash, sample_index))
            zsnd_file.write(pack(sound_format, sound['sample_index'], 4096, 127, sound['flags'], 127, byte_11, byte_19_20_21, byte_19_20_21, byte_19_20_21))

        for sample_index, sample in enumerate(json_samples):
            sample_file_path = Path(sample['file'])
            sample_file_name = sample_file_path.stem.upper()
            sample_rate = sample['sample_rate']
            sample_flags = sample['flags'] if ('flags' in sample) else 0
            channels = get_channels(sample_flags)

            sample_hashes.append((pjw_hash(f'CHARS3/7R/{zsnd_name}/{sample_file_name}'), sample_index))
            sample_file_hashes.append((pjw_hash(f'FILE/{zsnd_name}/{sample_file_name}'), sample_index))

            zsnd_file.seek(samples_offset + sample_index * get_sample_size(platform))

            if is_psx:
                zsnd_file.write(pack(sample_format, sample_index, rate2pitch(sample_rate), sample_flags))
            else:
                zsnd_file.write(pack(sample_format, sample_index, sample_flags, sample_rate))

            with sample_file_path.open(mode='rb') as sample_file:
                if is_psx and channels == 1:
                    sample_file.seek(vag_header_size)
                
                if platform == 'PC' and channels == 1:
                    with wave.open(sample_file, 'rb') as wav_file:
                        sample_file_data = wav_file.readframes(wav_file.getnframes())

                        if sample['format'] == 106:
                            sample_file_data = adpcm.encode(sample_file_data)
                else:
                    sample_file_data = sample_file.read()

                sample_file_size = len(sample_file_data)

                zsnd_file.seek(0, 2)
                sample_file_offset = zsnd_file.tell()
                zsnd_file.write(sample_file_data)

                if sample_index != (sample_count - 1):
                    zsnd_file.write(pack(f'{multipleOf(sample_file_size, 4 if (platform == "GCUB") else 16) - sample_file_size}x'))

                zsnd_file.seek(sample_files_offset + sample_index * get_sample_file_size(platform))

                if is_psx:
                    zsnd_file.write(pack(sample_file_format, sample_file_offset, sample_file_size))
                elif platform == 'GCUB':
                    zsnd_file.write(pack(sample_file_format, sample_file_offset, sample_file_size, b'DSP '))
                else:
                    zsnd_file.write(pack(sample_file_format, sample_file_offset, sample_file_size, sample['format'], sample_file_path.name.encode('utf-8')))

        sound_hashes.sort(key=itemgetter(0))
        sample_hashes.sort(key=itemgetter(0))
        sample_file_hashes.sort(key=itemgetter(0))

        zsnd_file.seek(sound_hashes_offset)

        for sound_hash in sound_hashes:
            zsnd_file.write(pack(hash_format, *sound_hash))

        zsnd_file.seek(sample_hashes_offset)

        for sample_hash in sample_hashes:
            zsnd_file.write(pack(hash_format, *sample_hash))

        zsnd_file.seek(sample_file_hashes_offset)

        for sample_file_hash in sample_file_hashes:
            zsnd_file.write(pack(hash_format, *sample_file_hash))

        zsnd_file.seek(0, 2)
        size = zsnd_file.tell()
        zsnd_file.seek(8)
        zsnd_file.write(pack(zsnd_size_big_fmt if (is_big_endian(platform)) else zsnd_size_fmt, size))

def decompile(zsnd_path: Path, output_path: Path):
    with output_path.open(mode='w', encoding='utf-8') as json_file:
        json.dump(read_zsnd(zsnd_path, output_path), json_file, indent=4)

def compile(json_path: Path, output_path: Path):
    with json_path.open(mode='r', encoding='utf-8') as json_file:
        write_zsnd(json.load(json_file), output_path)

def main():
    parser = ArgumentParser()
    parser.add_argument('-d', '--decompile', action='store_true', help='decompile input ZSND file to JSON file')
    parser.add_argument('input', help='input file (supports glob)')
    parser.add_argument('output', help='output file (wildcards will be replaced by input file name)')
    args = parser.parse_args()
    input_files = glob.glob(glob.escape(args.input), recursive=True)

    if not input_files:
        raise ValueError('No files found')

    for input_file in input_files:
        input_file = Path(input_file)
        output_file = Path(args.output.replace('*', input_file.stem))
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if args.decompile:
            decompile(input_file, output_file)
        else:
            compile(input_file, output_file)

if __name__ == '__main__':
    main()