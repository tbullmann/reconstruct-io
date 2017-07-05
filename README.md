# Data Exchange with Reconstruct/Win 1.1.0.1

XML input/output to png for data exchange with [Reconstruct Annotation Software](https://synapseweb.clm.utexas.edu/software-0).
Generated XML files is verified using the corresponding SERIES.DTD and SECTION.DTD files obtained from this [repository](https://github.com/meawoppl/reconstruct-1101) which contains a snapshot (Aug 11, 2011) of the source code for Reconstruct version 1.1.0.1 from http://tech.groups.yahoo.com/group/reconstruct_developers/files/

Currently only import/export of section XML is implemented.

For use from command line, see [here](doc/HOWTO.md).

## Prerequisites
- Linux or OSX
- Python 2 or Python 3

## Requirements
- Skiimage
- Matplotlib

## Preferred
- Anaconda Python distribution
- PyCharm

## TODO
- Add support fro series XML
- Test import into Reconstruct/Win