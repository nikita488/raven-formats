import glob
from argparse import ArgumentParser
from os.path import splitext
from pathlib import Path
from raven_formats.xmlb import read_xmlb, write_xmlb
from struct import Struct
import xml.etree.ElementTree as ET

FBFileHeader = Struct(
    '128s' # file path
    '64s' # file type
    'I' # file size
)

XML_F = ('xml', 'eng', 'fre', 'ger', 'ita', 'spa', 'rus', 'pol')
XML_Formats = [x for f in XML_F for x in (f'.{f}', f'.{f}b')]
RF_Revised = ('.chrb', '.navb', '.boyb', '.pkgb', '.sdfb')

Known_Formats = {
    'actors.igb': 'actorskin',
    'anim.igb': 'actoranimdb',
    'textures.igb': 'texture',
    'conversations.xmlb': 'xml',
    'data.xmlb': 'xml',
    'aipatterns.xml': 'aipatterns',
    'entities.xmlb': 'xml',
    'fightstyles.xmlb': 'fightstyle',
    'powerstyles.xmlb': 'fightstyle',
    'talents.xmlb': 'xml_talents',
    'weapons.xmlb': 'xml',
    'shared_nodes.xmlb': 'fightstyle_xml',
    'effects.xmlb': 'effect',
    'maps.xmlb': 'zonexml',
    'motionpaths.igb': 'motionpath',
    'common_ents.xmlb': 'common_ents',
    'item_ents.xmlb': 'item_ents',
    'shared_nodes.xmlb': 'shared_nodes',
    'shared_nodes_combat.xmlb': 'shared_nodes_combat',
    'shared_powerups.xmlb': 'shared_powerups',
    '.xmlb': 'xml_resident',
    '.igb': 'model',
    '.py': 'script',
    '.chrb': 'characters',
    '.chr': 'characters',
    '.navb': 'nav',
    '.nav': 'nav',
    '.boyb': 'boy',
    '.boy': 'boy',
    '.pkgb': 'pkg',
    '.pkg': 'pkg',
    '.zam': 'zam',
    '.shd': 'shadow',
    '.sdfb': 'sdf',
    '.sdf': 'sdf'
}
# Reversed dict in order and key/value. Order because the first identical value must be used as key.
Known_Types = dict(zip(list(Known_Formats.values())[::-1], list(Known_Formats.keys())[::-1]))
Known_Extensions = {k[k.index('.'):] for k in Known_Formats.keys()} | {f for f in XML_Formats}

Formats_With_Dir = {
    'actorskin': 'actors/',
    'actoranimdb': 'actors/',
    'effect': 'effects/'
}

Formats_Without_File = (
    'bigconvmap',
    'combat_is',
    'sound' # sounds are hashes only, and sound files are in separate ZSM/ZSS, even on consoles with FB packages
)

def decompile(fb_path: Path, output_path: Path, packagesrelative: bool):
    entries = ET.Element('packagedef')

    output_dir = output_path.parent / output_path.stem
    if packagesrelative:
        try:
            output_dir = output_path.parents[output_path.parts[::-1].index('packages')]
        except:
            print(f"WARNING: Directory 'packages' not detected in '{output_path}'. Extracting to '{output_dir}'.")
    with fb_path.open('rb') as fb_file:
        while (file_header := fb_file.read(FBFileHeader.size)):
            file_path, file_type, file_size = FBFileHeader.unpack(file_header)
            file_path = file_path.decode('utf-8').rstrip('\u0000')
            file_type = file_type.decode('utf-8').rstrip('\u0000')
            file_data = fb_file.read(file_size)

            # Note: Could do removeprefix('actors/') w/o lstrip, but this wouldn't remove leading '/'
            file_info, _ = splitext(file_path.lower().removeprefix('actors').removeprefix('effects').lstrip('/'))
            if not any(e.attrib['filename'] == file_info for e in entries.findall(f'./{file_type}')):
                child = ET.SubElement(entries, file_type)
                # child.text = str(file_info) # inner text
                child.set('filename', file_info) # attribute

            if file_type not in Formats_Without_File:
                file_path = output_dir / file_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(file_data)

    if output_path.suffix.lower() == '.pkgb':
        write_xmlb(entries, output_path)
    else:
        ET.indent(entries, ' ' * 4)
        ET.ElementTree(entries).write(output_path, encoding='utf-8')

def compile(xml_path: Path, output_path: Path, rebuild: bool, packagesrelative: bool):
    if rebuild: added_files = []
    entries = (read_xmlb(xml_path) if xml_path.suffix.lower() == '.pkgb' else
               ET.parse(xml_path)) if not rebuild or xml_path.is_file() else \
               ET.Element('packagedef')

    input_dir = xml_path.parent / xml_path.stem
    if packagesrelative:
        try:
            input_dir = xml_path.parents[xml_path.parts[::-1].index('packages')]
        except:
            print(f"WARNING: Directory 'packages' not detected in '{xml_path}'. Searching files in '{input_dir}'.")
    with output_path.open('wb') as fb_data:
        for e in entries.findall("./*"):
            file_path = e.attrib['filename']
            file_type = e.tag.lower()
            if Dir := Formats_With_Dir.get(file_type):
                if not file_path.lower().startswith(Dir):
                    file_path = Dir + file_path
            if file_type in Formats_Without_File:
                fb_data.write(FBFileHeader.pack(file_path.encode(), file_type.encode(), 0))
                continue
            file_info, ext = splitext(file_path)
            if ext in Known_Extensions:
                ext = (ext,)
            elif ext := Known_Types.get(file_type):
                ext = f'.{ext.rsplit('.', maxsplit=1)[1]}'
                ext = XML_Formats if ext in XML_Formats else \
                      (ext[:-1], ext) if ext in RF_Revised else (ext,)
            else:
                print(f"WARNING: Unknown file type '{file_type}'. '{file_path}' not packed.")
                continue

            Any = False
            for e in ext:
                file_path = file_info + e
                full_file_path = input_dir / file_path
                if full_file_path.exists():
                    Any = True
                    if rebuild: added_files.append(full_file_path)
                    file_data = full_file_path.read_bytes()

                    fb_data.write(FBFileHeader.pack(file_path.encode(), file_type.encode(), len(file_data)))
                    fb_data.write(file_data)

            if not Any:
                print(f"WARNING: File '{file_path}' not found and not packed.")

        if rebuild:
            packages = input_dir / 'packages'
            for f in input_dir.rglob("*.*"):
                if f in added_files or f.is_relative_to(packages): continue
                file_path = f.relative_to(input_dir)
                if (e := f.suffix.lower()) in XML_Formats: e = '.xmlb'
                f1, f2 = (file_path.parts + ('', ''))[:2]
                dp, ext = splitext(f2)
                # Note: isdigit allows exponents, but animations always include letters anyway
                type_string = (f2 if f1 == 'data' and not ext else
                               dp if dp == 'shared_powerups' else
                               'shared_nodes' if dp[:12] == 'shared_nodes' else
                               'anim' if f1 == 'actors' and not f.stem.isdigit() else
                               f1) + e
                file_type = Known_Formats[type_string] \
                                if type_string in Known_Formats else \
                            Known_Formats.get(e, 'unknown')
                file_data = f.read_bytes()
    
                fb_data.write(FBFileHeader.pack(file_path.as_posix().lower().encode(), file_type.encode(), len(file_data)))
                fb_data.write(file_data)

def main():
    parser = ArgumentParser()
    parser.add_argument('-d', '--decompile', action='store_true', help='decompile input FB file to XML package and extract all files')
    parser.add_argument('-r', '--rebuild', action='store_true', help='compile to FB file, including all files that exist in the corresponding directory')
    parser.add_argument('-p', '--packagesrelative', action='store_true', help='compile from and decompile to folders relative from packages parent folder')
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
            decompile(input_file, output_file, args.packagesrelative)
        else:
            compile(input_file, output_file, args.rebuild, args.packagesrelative)

if __name__ == '__main__':
    main()