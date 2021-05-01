# Raven Formats
[![MarvelMods](https://i.imgur.com/qoCxdy8t.png)](http://marvelmods.com)

Tools to work with formats used by **Raven Software** in **MUA/XML2** games.
## Usage
#### XMLB Compile/Decompile
```
xmlb [-h] [-d] input output

positional arguments:
  input            input file (supports glob)
  output           output file (wildcards will be replaced by input file name)

optional arguments:
  -h, --help       show this help message and exit
  -d, --decompile  decompile input XMLB file to JSON
```