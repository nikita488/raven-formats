import json, glob
from pathlib import Path
from argparse import ArgumentParser
from struct import pack, unpack, calcsize
import xml.etree.ElementTree as ET

header_fmt = '< 2I' #magic_number, version
header_size = calcsize(header_fmt)

element_fmt = '< I 2i I' #name_offset, next_element_offset, sub_element_offset, attr_count
element_size = calcsize(element_fmt)

attr_fmt = '< 2I' #name_offset, value_offset
attr_size = calcsize(attr_fmt)

def read_string(xmlb_file, offset: int) -> str:
    last_pos = xmlb_file.tell()
    string = b''

    xmlb_file.seek(offset)

    while char := xmlb_file.read(1):
        if char == b'\x00':
            break
        string += char
        
    xmlb_file.seek(last_pos)
    return string.decode('cp1252')

def read_element(xmlb_file) -> tuple[ET.Element, int]:
    name_offset, next_element_offset, sub_element_offset, attr_count = unpack(element_fmt, xmlb_file.read(element_size))
    element = ET.Element(read_string(xmlb_file, name_offset))
    offset = -1
    
    for i in range(attr_count):
        name_offset, value_offset = unpack(attr_fmt, xmlb_file.read(attr_size))
        element.set(read_string(xmlb_file, name_offset), read_string(xmlb_file, value_offset))

    if sub_element_offset != -1:
        xmlb_file.seek(sub_element_offset)
        sub_element, offset = read_element(xmlb_file)
        element.append(sub_element)

    while offset != -1:
        xmlb_file.seek(offset)
        next_element, offset = read_element(xmlb_file)
        element.append(next_element)

    return (element, next_element_offset)

def read_xmlb(xmlb_path: Path) -> ET.Element:
    with xmlb_path.open(mode='rb') as xmlb_file:
        magic_number, version = unpack(header_fmt, xmlb_file.read(header_size))

        if magic_number != 0x11B1 or version != 1:
            raise ValueError('Invalid magic number')
        
        root_element, next_element_offset = read_element(xmlb_file)
        return root_element

#http://effbot.org/zone/element-lib.htm#prettyprint
def indent(elem, level=0):
    i = "\n" + level*"    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

#https://stackoverflow.com/a/29520802/15020406
class FakeDict(dict):
    def __init__(self, items):
        self['something'] = 'something'
        self._items = items
    def items(self):
        return self._items

def str2value(string: str):
    value = string

    try:
        value = int(value)

        if len(str(value)) < len(string):
            value = string
    except ValueError:
        try:
            value = float(value)
        except ValueError:
            if value == 'true':
                value = True
            elif value == 'false':
                value = False
    return value

def to_json_element(element: ET.Element) -> tuple[str, FakeDict]:
    elements = []

    for name, value in element.items():
        elements.append((name, str2value(value)))

    for sub_element in element:
        elements.append(to_json_element(sub_element))

    return (element.tag, FakeDict(elements))

def decompile(xmlb_path: Path, output_path: Path, has_indent: bool):
    root_element = read_xmlb(xmlb_path)

    to_xml_json(root_element, output_path, has_indent)

def to_xml_json(root_element: ET.Element, output_path: Path, has_indent: bool):

    if output_path.suffix == '.xml':
        if has_indent:
            indent(root_element)
        ET.ElementTree(root_element).write(output_path, encoding='utf-8')
    elif output_path.suffix == '.json':
        with output_path.open(mode='w', encoding='utf-8') as json_file:
            json.dump(FakeDict([to_json_element(root_element)]), json_file, indent=4 if (has_indent) else None, ensure_ascii=False)
    else:
        raise ValueError(f'Output file extension {output_path.suffix} is not supported. Supported: .xml, .json')

string_offsets = {}
next_string_offset = header_size

def get_offset(key: str) -> int:
    global next_string_offset

    if key not in string_offsets:
        string_offsets[key] = next_string_offset
        next_string_offset += len(key) + 1
    
    return string_offsets[key]

def write_element(xmlb_file, element: ET.Element, has_next: bool):
    attr_count = len(element.attrib)
    sub_element_count = len(element)
    sub_element_offset = xmlb_file.tell() + element_size + attr_count * attr_size if (sub_element_count > 0) else -1

    if has_next:
        next_element_offset = xmlb_file.tell()

        for sub_element in element.iter():
            next_element_offset += element_size + len(sub_element.attrib) * attr_size
    else:
        next_element_offset = -1

    xmlb_file.write(pack(element_fmt, get_offset(element.tag), next_element_offset, sub_element_offset, attr_count))

    for name, value in element.items():
        xmlb_file.write(pack(attr_fmt, get_offset(name), get_offset(value)))

    for sub_element_index, sub_element in enumerate(element):
        write_element(xmlb_file, sub_element, sub_element_index < sub_element_count - 1)

def write_xmlb(root_element: ET.Element, output_path: Path):
    global next_string_offset

    with output_path.open(mode='wb') as xmlb_file:
        for element in root_element.iter():
            next_string_offset += element_size + len(element.attrib) * attr_size

        xmlb_file.write(pack(header_fmt, 0x11B1, 1))
        write_element(xmlb_file, root_element, False)

        for key in string_offsets:
            xmlb_file.write(key.encode('cp1252'))
            xmlb_file.write(b'\x00')

        string_offsets.clear()
        next_string_offset = header_size

def parse_json_object_pairs(pairs):
    return pairs

def value2str(value) -> str:
    if isinstance(value, str):
        return value

    string = str(value)
    return string.lower() if (isinstance(value, bool)) else string

def from_json_element(element: tuple) -> ET.Element:
    tag, sub_elements = element
    xml_element = ET.Element(tag)

    for element in sub_elements:
        tag, value = element
        
        if isinstance(value, list):
            xml_element.append(from_json_element(element))
        else:
            xml_element.set(tag, value2str(value))

    return xml_element

# function to process new lines from converter by BaconWizard17
def convert_escape(old_line):
    new_line = old_line.replace('\\', '\\\\')
    new_line = new_line.replace('"', '\\"')
    new_line = '"' + new_line
    return new_line

# NBA2kStuff's format to JSON converter by BaconWizard17
def from_xml_json(file) -> str:
    lines_output = []
    indent = 8
    for line in file:
        # format B does not have blank lines, so they can be skipped
        if line.isspace() == False:

            # leading (indent) and trailing spaces can be removed
            working_line = line.strip()

            # begin performing conversion
            if (working_line[0:4] == 'XMLB') and (working_line[-1] == '{'):
                # this is for the header
                lines_output.append('{')
                lines_output.append((' ' * 4) + '"' + working_line[4:-1].strip() + '": {')
            elif working_line == '}':
                # this deals with lines that are closing brackets. Their indent is less than the previous line
                indent -= 4
                # previous line does not need to end in a comma
                lines_output[-1] = lines_output[-1].strip(',')
                lines_output.append((' ' * indent) + '},')
            elif working_line[-1] == '{':
                # this deals with lines with open brackets. They increase the indent
                working_line = convert_escape(working_line)
                lines_output.append((' ' * indent) + working_line[:-1].strip() + '": {')
                indent += 4
            else:
                working_line = convert_escape(working_line)
                working_line = working_line.replace(' = ', '": "', 1)
                if working_line[-1] == ';': working_line = working_line[:-1].strip()
                lines_output.append((' ' * indent) + working_line + '",')

    # if a full file is being converted, need to add an extra bracket because header is now 2 lines (+ remove previous comma)
    if lines_output[0] == '{':
        lines_output[-1] = lines_output[-1].strip(',')
        lines_output.append('}')

    jstring = '\n'.join(lines_output)

    return jstring

def from_any_element(input_path: Path) -> ET.Element:
    # utf-8-sig should remove the BOM if present.
    with input_path.open(mode='r', encoding='utf-8-sig') as input_file:
        pos = input_file.tell()
        first_char = input_file.read(1)
        input_file.seek(pos)
        if first_char == '<':
            return ET.fromstring(input_file.read())
        else:
            data = ''
            if first_char == '{':
                data = json.load(input_file, object_pairs_hook=parse_json_object_pairs)
            else:
                # assuming it's NBA2kStuff's format
                json_data = from_xml_json(input_file)
                try:
                    data = json.loads(json_data, object_pairs_hook=parse_json_object_pairs)
                except:
                    # Give the user the json data, if there was an error.
                    path_json = input_path.with_suffix('.json')
                    with path_json.open(mode='w') as file_json:
                        file_json.write(json_data)
                    raise

            root_amount = len(data)

            if root_amount != 1:
                raise ValueError(f'Found {root_amount} root elements. Required 1')

            return from_json_element(data[0])

def compile(input_path: Path, output_path: Path):
    element = from_any_element(input_path)
    write_xmlb(element, output_path)

def convert(input_path: Path, output_path: Path, has_indent: bool):
    element = from_any_element(input_path)
    to_xml_json(element, output_path, has_indent)

def main():
    parser = ArgumentParser()
    parser.add_argument('-c', '--convert', action='store_true', help='convert decompiled input file to XML/JSON file')
    parser.add_argument('-d', '--decompile', action='store_true', help='decompile input XMLB file to XML/JSON file')
    parser.add_argument('--no_indent', action='store_true', help='disable indent in decompiled XML/JSON file')
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
            decompile(input_file, output_file, not args.no_indent)
        elif args.convert:
            convert(input_file, output_file, not args.no_indent)
        else:
            compile(input_file, output_file)

if __name__ == '__main__':
    main()
