from dataclasses import InitVar, dataclass
from enum import Enum
from struct import Struct, pack
import json, wave, glob
from operator import itemgetter
from pathlib import Path
from argparse import ArgumentParser
from . import adpcm

@dataclass
class Header:
    size: int = 0
    header_size: int = 0
    sound_count: int = 0
    sound_hashes_offset: int = 0
    sounds_offset: int = 0
    sample_count: int = 0
    sample_hashes_offset: int = 0
    samples_offset: int = 0
    sample_file_count: int = 0
    sample_file_hashes_offset: int = 0
    sample_files_offset: int = 0
    phrase_count: int = 0
    phrase_hashes_offset: int = 0
    phrases_offset: int = 0
    track_def_count: int = 0
    track_def_hashes_offset: int = 0
    track_defs_offset: int = 0
    reserved_count: int = 0
    reserved_hashes_offset: int = 0
    reserved_offset: int = 0
    keymap_count: int = 0
    keymap_hashes_offset: int = 0
    keymaps_offset: int = 0

class platform_info(Enum):
    PC   = 'PC',   '<', '2H I 16x', '3I 64s'
    PS2  = 'PS2',  '<', '3H 10x',   '2I'
    XBOX = 'XBOX', '<', '2H I 20x', '3I 8x 64s'
    GCUB = 'GCUB', '>', '2H I 16x', '2I 4s'
    PS3  = 'PS3',  '>', '3H 10x',   '2I'
    XENO = 'XENO', '>', '2H I 28x', '3I 8x 64s'
    def __new__(cls, value: str, E: str, sample_fmt: str, file_fmt: str):
        member = object.__new__(cls)
        member._value_ = value
        member.E = E
        member.sample_fmt = Struct(E + sample_fmt)
        member.sample_file_fmt = Struct(E + file_fmt)
        member.header_fmt = Struct(E + '23I')
        member.hash_fmt = Struct(E + '2I')
        member.sound_fmt = Struct(E +
            '2H' # sample index & pitch
            'B'  # 127 (?)
            'x'  # padding?
            'B'  # sound flags
            '2x' # padding?
            'B'  # 127 (?)
            'x'  # padding?
            'B'  # 127 (?), 15 if PSX
            '7x' # padding?
            '3B' # 0 (?), 32 if PS3
            '2x' # padding?
        )
        return member

vag_header_fmt = Struct(
    '>'   # big endian
    '4s'  # 'VAGp'
    'I'   # header size w/o file name (0x20)
    '4x'  # padding?
    '2I'  # sample_file_size & sample_rate
    '12x' # padding?
    '16s' # file name (number)
)

@dataclass
class SampleFile:
    platform: InitVar[str]
    sample_index: InitVar[int]
    offset: int
    size: int
    format: int = -1
    name: str = ''
    def __post_init__(self, platform: str, sample_index: int):
        if platform in ('PC', 'XBOX', 'XENO'):
            self.name = self.name.decode('utf-8').rstrip('\u0000')
        else:
            self.name = f'{sample_index}{".dsp" if platform == 'GCUB' else ".vag"}'

@dataclass
class Sample:
    platform: InitVar[str]
    unknown: int
    flags: int
    rate: int
    def __post_init__(self, platform: str):
        if platform in ('PS2', 'PS3'):
            self.flags, self.rate = self.rate, pitch2rate(self.flags)

hash_strings = {}

def hash2str(sound_hash: int):
    global hash_strings

    if not hash_strings:
        from importlib.resources import files as lib_files
        from raven_formats import data
        with (lib_files(data) / 'zsnd_hashes.json').open('r') as hashes_file:
            hash_strings = json.load(hashes_file)

    key = str(sound_hash)
    return hash_strings[key] if key in hash_strings else sound_hash
    
def pjw_hash(key: str) -> int:
    hash = 0
    for c in key:
        hash = (hash << 4) + ord(c)
        test = hash & 0xF0000000
        if test:
            hash = (hash ^ (test >> 24)) & (~0xF0000000)
    return hash & 0x7FFFFFFF

def pitch2rate(pitch: int) -> int:
    rate = pitch * 44100 / 4096
    return int(rate if rate.is_integer() else round(rate, -1))

def rate2pitch(rate: int) -> int:
    return round(rate * 4096 / 44100)

def get_channels(sample_flags: int) -> int:
    return 4 if sample_flags & 32 else 2 if sample_flags & 2 else 1

def read_zsnd(zsnd_path: Path, output_path: Path) -> dict:
    with zsnd_path.open(mode='rb') as zsnd_file:
        if (zsnd_file.read(4) != b'ZSND'):
            raise ValueError('Invalid magic number')

        platform = platform_info(zsnd_file.read(4).decode('utf-8').rstrip())
        # ValueError: ... is not a valid platform_info

        header = Header(*platform.header_fmt.unpack(zsnd_file.read(platform.header_fmt.size)))
        
        if header.sound_count == 0 or header.sample_count == 0 or header.sample_file_count == 0:
            return

        zsnd_file.seek(header.sound_hashes_offset)

        sound_hashes = list(platform.hash_fmt.iter_unpack(zsnd_file.read(platform.hash_fmt.size * header.sound_count)))
        sound_hashes.sort(key=itemgetter(1))

        zsnd_file.seek(header.sounds_offset)

        sounds = [
            {
                'hash': hash2str(sound_hashes[i][0]),
                'sample_index': sound[0],
                'flags': sound[3]
            }
            for i, sound in enumerate(platform.sound_fmt.iter_unpack(zsnd_file.read(platform.sound_fmt.size * header.sound_count)))
        ]

        zsnd_file.seek(header.sample_files_offset)
        sample_files = (SampleFile(platform.value, i, *d) for i, d in enumerate(platform.sample_file_fmt.iter_unpack(zsnd_file.read(platform.sample_file_fmt.size * header.sample_count))))

        zsnd_file.seek(header.samples_offset)
        samples = []
        for s in platform.sample_fmt.iter_unpack(zsnd_file.read(platform.sample_fmt.size * header.sample_count)):
            sample_file = next(sample_files)
            sample = Sample(platform.value, *s)

            sample_file_path = output_path.parent / output_path.stem / sample_file.name
            sample_file_path.parent.mkdir(parents=True, exist_ok=True)
            sample_file_name = sample_file_path.stem

            counter = 1
            while sample_file_path.exists():
                sample_file_path = sample_file_path.with_stem(f'{sample_file_name}_{counter}')
                counter += 1

            sample_data = {
                'file': str(sample_file_path)
            }
            if sample_file.format > -1:
                sample_data['format'] = sample_file.format
            sample_data['sample_rate'] = sample.rate
            if sample.flags > 0:
                sample_data['flags'] = sample.flags

            samples.append(sample_data)

            zsnd_file.seek(sample_file.offset)
            channels = get_channels(sample.flags)

            sample_file_data = zsnd_file.read(sample_file.size)
  
            if platform.value == 'PC' and channels == 1:
                with wave.open(str(sample_file_path), 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample.rate)

                    if sample_file.format == 106:
                        wav_file.writeframes(adpcm.decode(sample_file_data))
                    else:
                        wav_file.writeframes(sample_file_data)
            else:
                with sample_file_path.open(mode='wb') as file:
                    if platform.value in ('PS2', 'PS3') and channels == 1:
                        file.write(vag_header_fmt.pack(
                            b'VAGp',
                            0x20,
                            sample_file.size,
                            sample.rate,
                            sample_file_path.stem.encode('utf-8')
                        ))
                    sample_file.write(sample_file_data)

        return {
            'platform': platform.value,
            'sounds': sounds,
            'samples': samples
        }

def write_zsnd(data: dict, output_path: Path):
    with output_path.open(mode='wb') as zsnd_file:
        json_sounds = data['sounds']
        json_samples = data['samples']
        sound_count = len(json_sounds)
        sample_count = len(json_samples)

        if (sample_count - 1) >> 16:
            raise ValueError(f'Sample count of {sample_count} surpasses the maximum of {0xFFFF + 1}')

        zsnd_name = output_path.stem.upper()
        platform = platform_info(data['platform'])
        is_psx = platform.value in ('PS2', 'PS3')

        hash_sz = sample_count * platform.hash_fmt.size
        sound_h_o = 8 + platform.header_fmt.size
        sounds_o = sound_h_o + sound_count * platform.hash_fmt.size
        sample_h_o = sounds_o + sound_count * platform.sound_fmt.size
        samples_o = sample_h_o + hash_sz
        sample_fh_o = samples_o + sample_count * platform.sample_fmt.size
        sample_f_o = sample_fh_o + hash_sz
        header_sz = sample_f_o + sample_count * platform.sample_file_fmt.size
        if platform.value != 'GCUB':
            header_sz = header_sz // -16 * -16

        header = Header(
            header_size=header_sz,
            sound_count=sound_count,
            sound_hashes_offset=sound_h_o,
            sounds_offset=sounds_o,
            sample_count=sample_count,
            sample_hashes_offset=sample_h_o,
            samples_offset=samples_o,
            sample_file_count=sample_count,
            sample_file_hashes_offset=sample_fh_o,
            sample_files_offset=sample_f_o,
            phrase_hashes_offset=header_sz,
            phrases_offset=header_sz,
            track_def_hashes_offset=header_sz,
            track_defs_offset=header_sz,
            reserved_hashes_offset=header_sz,
            reserved_offset=header_sz,
            keymap_hashes_offset=header_sz,
            keymaps_offset=header_sz
        )

        zsnd_file.write(
            b'ZSND' +
            platform.value.ljust(4).encode('utf-8') +
            platform.header_fmt.pack(*vars(header).values()) +
            bytes(header_sz - sound_h_o)
        )

        zsnd_file.seek(sounds_o)

        sound_hashes = [
            (
                pjw_hash(sound['hash'].upper()) if isinstance(sound['hash'], str) else sound['hash'],
                sample_index
            )
            for sample_index, sound in enumerate(json_sounds)
        ]
        byte_19_20_21 = 32 if platform.value == 'PS3' else 0
        zsnd_file.write(b''.join(
            platform.sound_fmt.pack(
                sound['sample_index'],
                4096,
                127,
                min(sound['flags'], 255),
                127,
                15 if is_psx else 127,
                byte_19_20_21, byte_19_20_21, byte_19_20_21
            )
            for sound in json_sounds
        ))

        sample_hashes = []

        for sample_index, sample in enumerate(json_samples):
            sample_file_path = Path(sample['file'])
            sample_file_name = sample_file_path.stem.upper()
            sample_rate = sample['sample_rate']
            sample_flags = sample['flags'] if ('flags' in sample) else 0
            channels = get_channels(sample_flags)

            sample_hashes.append((f'/{zsnd_name}/{sample_file_name}', sample_index))

            zsnd_file.seek(samples_o + sample_index * platform.sample_fmt.size)

            if is_psx:
                zsnd_file.write(platform.sample_fmt.pack(sample_index, rate2pitch(sample_rate), sample_flags))
            else:
                zsnd_file.write(platform.sample_fmt.pack(sample_index, sample_flags, sample_rate))

            with sample_file_path.open(mode='rb') as sample_file:
                if is_psx and channels == 1:
                    sample_file.seek(vag_header_fmt.size)
                
                if platform.value == 'PC' and channels == 1:
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

                if sample_index != sample_count - 1:
                    align = 4 if platform.value == 'GCUB' else 16
                    zsnd_file.write(pack(f'{sample_file_size // -align * -align - sample_file_size}x'))

                zsnd_file.seek(header.sample_files_offset + sample_index * platform.sample_file_fmt.size)

                sample_file_format = () if is_psx else \
                                     (b'DSP ',) if platform.value == 'GCUB' else \
                                     (sample['format'], sample_file_path.name.encode('utf-8'))
                zsnd_file.write(platform.sample_file_fmt.pack(
                    sample_file_offset,
                    sample_file_size,
                    *sample_file_format
                ))

        sound_hashes.sort(key=itemgetter(0))
        sample_hashes.sort(key=itemgetter(0))
        sample_hash_format = f'{platform.E}{sample_count * 2}I'

        zsnd_file.seek(header.sound_hashes_offset)

        zsnd_file.write(pack(f'{platform.E}{sound_count * 2}I', *(i for s in sound_hashes for i in s)))

        zsnd_file.seek(header.sample_hashes_offset)
        
        zsnd_file.write(pack(
            sample_hash_format,
            *(i for s in sample_hashes for i in (pjw_hash('CHARS3/7R' + s[0]), s[1]))
        ))

        zsnd_file.seek(header.sample_file_hashes_offset)

        zsnd_file.write(pack(
            sample_hash_format,
            *(i for s in sample_hashes for i in (pjw_hash('FILE' + s[0]), s[1]))
        ))

        zsnd_file.seek(0, 2)
        size = zsnd_file.tell()
        zsnd_file.seek(8)
        zsnd_file.write(pack(f'{platform.E}I', size))

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
    input_files = glob.glob(args.input.replace('[', '[[]'), recursive=True)

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