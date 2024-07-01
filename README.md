# Raven Formats
[![MarvelMods](https://i.imgur.com/qoCxdy8t.png)](http://marvelmods.com)

Tools to work with formats used by **Raven Software** in **MUA/XML2** games.
## Usage
#### XMLB Compile/Decompile
```
usage: xmlb.py [-h] [-d] [--no_indent] input output

positional arguments:
  input            input file (supports glob)
  output           output file (wildcards will be replaced by input file name)

optional arguments:
  -h, --help       show this help message and exit
  -d, --decompile  decompile input XMLB file to XML/JSON file
  --no_indent      disable indent in decompiled XML/JSON file
```
#### ZSND Compile/Decompile
```
usage: zsnd.py [-h] [-d] input output

positional arguments:
  input            input file (supports glob)
  output           output file (wildcards will be replaced by input file name)

optional arguments:
  -h, --help       show this help message and exit
  -d, --decompile  decompile input ZSND file to JSON file
```

#### FB Compile/Decompile
```
usage: fb.py [-h] [-d] [-r] input output

positional arguments:
  input            input file (supports glob)
  output           output file (wildcards will be replaced by input file name)

optional arguments:
  -h, --help       show this help message and exit
  -d, --decompile  decompile input FB file to JSON file
  -r, --rebuild    compile to FB file, including all files that exist in the corresponding directory
```