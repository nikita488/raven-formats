import json, glob
from pathlib import Path
from argparse import ArgumentParser
from struct import Struct
from io import BytesIO

FBFileHeader = Struct(
    '128s' # file path
    '64s' # file type
    'I' # file size
)

def decompile(fb_path: Path, output_path: Path):
    fb_data = fb_path.read_bytes()

    with BytesIO(fb_data) as fb_file:
        entries = {}

        while (file_header := fb_file.read(FBFileHeader.size)):
            file_path, file_type, file_size = FBFileHeader.unpack(file_header)
            file_path = file_path.decode().split('\x00', 1)[0]
            file_type = file_type.decode().split('\x00', 1)[0]
            file_data = fb_file.read(file_size)
            
            entries[file_path] = file_type
            file_path = output_path.parent / output_path.stem / file_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(file_data)
        
        output_path.write_text(json.dumps(entries, indent=4))

def compile(json_path: Path, output_path: Path):
    json_data = json_path.read_text()
    json_data = json.loads(json_data)

    with BytesIO() as fb_data:
        for file_path, file_type in json_data.items():
            real_file_path = json_path.parent / json_path.stem / file_path
            file_data = real_file_path.read_bytes()
            fb_file_header = FBFileHeader.pack(file_path.encode(), file_type.encode(), len(file_data))
            
            fb_data.write(fb_file_header)
            fb_data.write(file_data)
        
        output_path.write_bytes(fb_data.getbuffer())

def main():
    parser = ArgumentParser()
    parser.add_argument('-d', '--decompile', action='store_true', help='decompile input FB file to JSON file')
    parser.add_argument('input', help='input file (supports glob)')
    parser.add_argument('output', help='output file (wildcards will be replaced by input file name)')
    args = parser.parse_args()
    input_files = glob.glob(args.input, recursive=True)

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