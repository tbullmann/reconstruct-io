from collections import namedtuple

import os
from lxml import etree, objectify
from collections import defaultdict
from xml.etree import cElementTree as ET, cElementTree
from xml.dom.minidom import parseString

from skimage.measure import find_contours, approximate_polygon, subdivide_polygon

try:
  basestring
except NameError:  # python3
  basestring = str

import numpy as np
from skimage.draw import polygon
from skimage.io import imread

SECTION_DTD_FILENAME = os.path.join(os.path.dirname(__file__), "SECTION.DTD")
SERIES_DTD_FILENAME = os.path.join(os.path.dirname(__file__), "SERIES.DTD")


def verify_files(xml_file, dtd_file):
    """
    Verify xml file against dtd file, given by file handles.
    """
    dtd = etree.DTD(dtd_file)
    tree = objectify.parse(xml_file)
    return dtd.validate(tree)

def verify(xml_filename, dtd_filename):
    """
    Verify xml file against dtd file, given by filenames.
    """
    dtd_file = open(dtd_filename, 'rb')
    xml_file = open(xml_filename, 'rb')
    return verify_files(xml_file, dtd_file)

# The following two function based on the answers posted on stackoverflow by K3--rnc (2012, 2016)
# http://stackoverflow.com/questions/2148119/how-to-convert-an-xml-string-to-a-dictionary-in-python

def etree_to_dict(t):
    """
    Parses XML to a JSON/dict. as well as attributes following this XML-to-JSON "specification":
    http://www.xml.com/pub/a/2006/05/31/converting-between-xml-and-json.html
    It is the most general solution handling all cases of XML.
    :param t:
    :return:
    """
    d = {t.tag: {} if t.attrib else None}
    children = list(t)
    if children:
        dd = defaultdict(list)
        for dc in map(etree_to_dict, children):
            for k, v in dc.items():
                dd[k].append(v)
        # d = {t.tag: {k:v[0] if len(v) == 1 else v for k, v in dd.items()}}
        # original line above makes children either dictionaries or list of dictionaries if there are more of same
        # However this is a hassle to process, therefore make them always lists, easier to parse
        # (and it does not break backward conversion)
        d = {t.tag: {k:v for k, v in dd.items()}}
    if t.attrib:
        d[t.tag].update(('@' + k, v) for k, v in t.attrib.items())
    if t.text:
        text = t.text.strip()
        if children or t.attrib:
            if text:
              d[t.tag]['#text'] = text
        else:
            d[t.tag] = text
    return d


def dict_to_xml_str(d):
    """
    Emit an (not so pretty) XML string from a JSON/dict.
    """
    def _to_etree(d, root):
        if not d:
            pass
        elif isinstance(d, basestring):
            root.text = d
        elif isinstance(d, dict):
            for k,v in d.items():
                assert isinstance(k, basestring)
                if k.startswith('#'):
                    assert k == '#text' and isinstance(v, basestring)
                    root.text = v
                elif k.startswith('@'):
                    assert isinstance(v, basestring)
                    root.set(k[1:], v)
                elif isinstance(v, list):
                    for e in v:
                        _to_etree(e, ET.SubElement(root, k))
                else:
                    _to_etree(v, ET.SubElement(root, k))
        else:
            raise TypeError('invalid type: ' + str(type(d)))
    assert isinstance(d, dict) and len(d) == 1
    tag, body = next(iter(d.items()))
    node = ET.Element(tag)
    _to_etree(body, node)
    return ET.tostring(node)


def prettify(rough_string):
    """
    Return a pretty-printed XML string by indentation and new lines.
    """
    reparsed = parseString(rough_string)
    return reparsed.toprettyxml(indent="\t")


# Import from XML

def convert_attribute_from_string (key, value):
    """
    Convert an value from string to appropriate datatype (e.g. as determine by key)
    """
    # <!ENTITY % SFBool   "(true|false)"> <!-- a single field Boolean -->
    if value=='true' or value =='false':
        return bool(value)

    # <!ENTITY % SFInt32  "CDATA">        <!-- a single 32-bit integer -->
    # if key in ['index', 'mode', 'dim']:
    #     return int(value)
    #
    # <!ENTITY % SFFloat  "CDATA">        <!-- a single 32-bit floating point value-->
    # if key in ['thickness', 'brightness', 'mag', 'contrast']:
    #     return float(value)
    #
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            pass   # Neither int or float

    # # <!ENTITY % MFVec2f  "CDATA">        <!-- an array of pairs of floats -->
    # if key in ['points']:  # split points on "," and coordinates on " "
    if ',' in value:
        points = map(lambda x: map(float, x.split()), value.split(','))
        if points[-1] == []:  # Remove empty coordinate pair introduced by a trailing "," (as in original xml files!)
            points.pop()
        return np.array(points)

    # <!ENTITY % SFColor  "CDATA">        <!-- RGB color as 3 floats where 0 0 0 is black and 1 1 1 is white -->
    # <!ENTITY % MFFloat  "CDATA">        <!-- an array of floats -->
    # if key in ['xcoef', 'ycoef', 'border', 'fill']:
    if ' ' in value:
        return np.array(map(float, value.split()))

    # <!ENTITY % SFString "CDATA">        <!-- a string of characters excluding '/','<','>','"' -->
    return value


def attributes_to_named_tuple(name, dictionary):
    """
    Convert a dictionary into a named tuple, but only for keys that represent "attributes" in the xml
    :param name: name of the named tuple
    :param dictionary: dictionary generated from xml using etree_to_dict, therefore attributes have keys start with @

    """
    attributes = {k[1:]: convert_attribute_from_string(k[1:], v)
                  for k, v in dictionary.items() if k.startswith('@')}
    return namedtuple(name, attributes.keys())(**attributes)


def read_section_dict(dictionary):
    """
    Extract the data as named tupel from the xml generated dictionary.
    Note: Assuming that there only two transformations, first for the image and second for the contours.
    That (order and simple structure) must not always be the case! There might be cases with multiple contours
    sets each in with its own transformation, as well as multiple images
    :param dictionary:
    :return:
    """
    section = attributes_to_named_tuple('Section', dictionary['Section'])

    i = 0
    try:
    # if 'Image' in dictionary['Section']['Transform'][i].keys():
        image_transform = attributes_to_named_tuple('Transforms', dictionary['Section']['Transform'][0])
        image = attributes_to_named_tuple('Image', dictionary['Section']['Transform'][0]['Image'][0])
        image_contour = attributes_to_named_tuple('Contour', dictionary['Section']['Transform'][0]['Contour'][0])
        i += 1
    except:
    # else:
        # No image described in xml
        image_transform = DefaultTransform
        image = DefaultImage
        image_contour = DefaultContour

    try:
    # if 'Contour' in dictionary['Section']['Transform'][i].keys():
        contours_transform = attributes_to_named_tuple('Transforms', dictionary['Section']['Transform'][i])
        contours = map(lambda x: attributes_to_named_tuple('Contours', x),
                       dictionary['Section']['Transform'][i]['Contour'])
    except:
    # else:
        # No contours described  in xml
        contours_transform = DefaultTransform
        contours = []

    return (section,
            image,
            image_contour,
            image_transform,
            contours,
            contours_transform)


# export to XML

# <!ATTLIST Contour
#     name       %SFString;  "unknown"
#     hidden     %SFBool;    "false"
#     closed     %SFBool;    "true"
#     simplified %SFBool;    "false"
#     border     %SFColor;   "1 0 1"
#     fill       %SFColor;   "1 0 1"
#     mode       %SFInt32;   "9"
#     comment    %SFString;  #IMPLIED
#     points     %MFVec2f;   #IMPLIED>
ContourAttrib = namedtuple('Contour', ["name", "hidden", "closed", "simplified",
                                       "border", "fill", "mode", "comment", "points"])
DefaultContour = ContourAttrib("unknown", False, True, False, [1, 0, 1], [1, 0, 1], 9, None, None)
ExampleImageContour = ContourAttrib("domain1", False, True, False, [1, 0, 1], [1, 0, 1], 11,
                                    None, [[0, 0], [3579, 0], [3579, 2467], [0, 2467]])
ExampleDendriteContour = ContourAttrib("unknown", False, True, True, [1, 0, 1], [1, 0, 1], -11,
    "dendrite0", [[6.85749, 8.26195], [6.87711, 8.19918],  [6.92026, 8.13641],  [6.98695, 8.01087],  [7.01442, 7.9481]])
TwoExampleDendriteContours = [ExampleDendriteContour, ExampleDendriteContour]

# <!ATTLIST Image
#     mag         %SFFloat;   "1.0"
#     contrast    %SFFloat;   "1"
#     brightness  %SFFloat;   "0"
#     red         %SFBool;    "true"
#     green       %SFBool;    "true"
#     blue        %SFBool;    "true"
#     src         %SFString;  ""
#     proxy_src	%SFString;  ""
#     proxy_scale %SFFloat;   "1.0">
ImageAttrib = namedtuple('Image',["mag", "contrast", "brightness", "red", "green", "blue", "src",
                                  "proxy_src", "proxy_scale"])
DefaultImage = ImageAttrib(1.0, 1, 0, True, True, True, "", "", 1.0)
ExampleImage = ImageAttrib(0.005, 1, 0, True, True, True, "image0373_(monitor126).bmp.tif", None, None)


# <!ATTLIST Transform
#     dim     %SFInt32;   "6"
#     xcoef   %MFFloat;   "0 1 0 0 0 0"
#     ycoef   %MFFloat;   "0 0 1 0 0 0">
TransformAttrib = namedtuple('Transform', ['dim', 'xcoef', 'ycoef'])
DefaultTransform = TransformAttrib (0, [0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0])

# <!ATTLIST Section
#     index     %SFInt32;   "-1"
#     thickness %SFFloat;   "0.05"
#     alignLocked %SFBool;  "false">
SectionAttrib = namedtuple('Section', ['alignLocked', 'index', 'thickness'])
DefaultSection = SectionAttrib (False, -1, 0.05)


def convert_attribute_to_string(key, value):
    """
    Convert attributes to strings, depending on the key and value type
    """
    if isinstance(value, bool):    # Note: make sure boolean is lower case as %SFBool
        return str(value).lower()
    if key in ['xcoef', 'ycoef', 'border', 'fill']:   # arrays of numbers
        return " ".join(map(str, value))
    if key in ['points']:   # coordinates separated with " ", points with ", "
        return ", ".join(map(lambda x: " ".join(map(str, x)), value))
    return str(value)


def attributes_to_dict(named_tuple):
    """
    Convert the attributes given as a named tuple into a dictionary with names as key.
    """
    return {"@"+k: convert_attribute_to_string(k,v)
            for k, v in named_tuple._asdict().items() if v is not None }


def make_section_dict(section=DefaultSection,
                      image=DefaultImage,
                      image_contour=ExampleImageContour,
                      image_transform=DefaultTransform,
                      contours=TwoExampleDendriteContours,
                      contour_transform = DefaultTransform):
    """
    Convert section tracing data to XML.
    Note: Assuming that all contours share the same transformation. That must not always be the case!
    :param section: named tuple containing section attributes, e.g. section index and thickness
    :param image: named tuple containing image attributes, e.g. filename
    :param image_contour: named tuple containing section contours attributes, e.g. corner points
    :param image_transform: named tuple containing the image transform attributes
    :param contours: a list of named tuples containing contour attributes, e.g. name and points
    :param contour_transform: named tuple containing the transform attributes applied to contours
    :return: dictionary of the section for conversion to xml
    """
    transform_list = []

    # <!ELEMENT Transform ((Image,Contour)|Contour+) >
    # Case 1: Transform contains Image and Contour
    transform_list.append(attributes_to_dict(image_transform))
    transform_list[0]['Image'] = [attributes_to_dict(image)]
    transform_list[0]['Contour'] = [attributes_to_dict(image_contour)]

    # <!ELEMENT Transform ((Image,Contour)|Contour+) >
    # Case 2: Transform contains Image and Contour
    transform_list.append(attributes_to_dict(contour_transform))
    transform_list[1]['Contour'] = map(attributes_to_dict, contours)

    # < !ELEMENT    Section(Transform +) >
    section_dict = attributes_to_dict(section)
    section_dict.update({'Transform': transform_list})

    return {'Section': section_dict}


def xml_to_label_dict(xml_filename):
    """
    Converts xml with contours to dictionary of label images.
    Notes:
    - This implementation works only if no transform is used
    - Points of the contour (domain) of the image are given in pixels (!) and must be convert by image
      attribute mag (magnification) which states the pixel width in micrometer
    - image must be at (0,0)
    :param xml_filename: path of xml file
    :return: labels: dictionary of label images with contour.name as key
             source_image: annotated image if available
    """
    e = open(xml_filename, 'r').read()
    e = ET.XML(e)
    d = etree_to_dict(e)
    section, image, image_contour, image_transform, contours, contours_transform = read_section_dict(d)

    assert image_transform.dim == 0 and contours_transform.dim == 0

    pixel_size = image.mag  # in micrometer

    minr, minc, maxr, maxc = bbox(image_contour.points)
    assert minc == 0 and minr == 0  # image corner at (0,0)

    # Make empty label map
    empty_label = np.zeros((maxr + 1, maxc + 1))

    # try reading annotated image and check shape is correct
    source_image = empty_label.copy()
    if image.src:
        image_file = os.path.join(os.path.dirname(xml_filename), image.src)
        if os.path.isfile(image_file):
            source_image = imread(image_file)
            assert source_image.shape == empty_label.shape

    # Iterate over all contours and plot them on a label image indexed by the name of the contour
    # Note: Disconnected cross sections contours of the same object are draw on the the same label image.
    labels = dict()
    for contour in contours:
        if contour.name not in labels.keys():
            labels[contour.name] = empty_label.copy()
        r = maxr - contour.points[:, 1] / pixel_size  # pixel row from y coordinates; image y axis inverted
        c = contour.points[:, 0] / pixel_size  # pixel column from x coordinates
        rr, cc = polygon(r, c, shape=(maxr, maxc))   # shape restrictes polygon when annotation larger than image (?)
        labels[contour.name][rr, cc] = 1

    return labels, source_image


def bbox(points, type=int):
    """
    Return the bounding box for a polygon.
    """
    # TODO: Find the skimage function.
    points = points.astype(type)
    return min(points[:, 1]), min(points[:, 0]), max(points[:, 1]), max(points[:, 0])


def labels_to_contours(label_dict, pixel_size, border_colors=None, fill_colors=None, fill_modes=None, tolerance=5, level=0):
    """
    Converts a dictionary of label images into list of contours.
    :param label_dict: dictionary with label images indexed by label name
    :param pixel_size: width of an pixel of the label images in micrometer
    :param border_colors: dictionary of border colors indexed by label name, if None use [1, 0, 1]
    :param fill_colors: dictionary of fill colors indexed by label name, if None use [1, 0, 1]
    :param fill_modes: dictionary of fill modes indexed by label name, if None use fill pattern 9
    :param tolerance: resolution for the contour polygon (see skimage.measure.approximate_polygon)
    :return: list of contours (contour attributes and list of points with coordinates of micrometers)
    """
    contours = []
    for label_name, image_label in label_dict.items():

        # invert imgae y axis, then transpose because contour coordinates exported as (y, x) not (x, y)
        image_label = np.flipud(image_label).T
        image_label = np.lib.pad(image_label, ((1, 1), (1, 1)), 'constant',  constant_values=((0,0),(0,0)))

        for contour_in_label_image in find_contours(image_label, level):
            # get coordinates of contour points and convert to micrometer units
            points = approximate_polygon(contour_in_label_image, tolerance=tolerance) * pixel_size

            # get border color, fill color and fill mode for each label from dictionary or use default
            border_color = border_colors[label_name] if border_colors else [1, 0, 1]
            fill_color = fill_colors[label_name] if fill_colors else [1, 0, 1]
            fill_mode = fill_modes[label_name] if fill_modes else 9

            if len(points) > 2:  # add contour if it has at least 3 points, to make an triangle
                contours.append(ContourAttrib(
                    label_name,
                    False,  # hidden
                    True,  # closed
                    False,  # simplified
                    border_color,
                    fill_color,
                    fill_mode,
                    None,  # comment
                    points))  # points

    return contours


def label_dict_to_xml_str(label_dict, image_shape, image_filename, pixel_size, section_thickness, section_index, **kwargs):
    """
    Converts a dictionary of label images into list of contours.
    Note: There is no support for transformation.
    :param label_dict: dictionary of the label images
    :param image_shape: shape of the annotated image
    :param image_filename: base file name of the annotated images (usually xml is placed in same directory)
    :param pixel_size: width of an pixel of the label images in micrometer
    :param section_thickness: thickness of the section in micrometer
    :param section_index: index of the section in the image stack
    :param kwargs: Additional parameters including label_dict, border_colors, fill_colors, fill_modes, resolution
           (for explanation see labels_to_contours)
    :return: string containing the xml
    """

    # Describe Section
    section = SectionAttrib(
        False,              # alignLocked
        section_index,     # index
        section_thickness)  # thickness'])

    # Describe Image
    image = ImageAttrib(
        pixel_size,      # mag
        1,               # contrast
        0,               # brightness
        True,            # red
        True,            # green
        True,            # blue
        image_filename,  # src
        None,            # proxy_src
        None)            # proxy_scale

    # Describe image contour
    h, w = image_shape
    image_points = np.array([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
    image_contour = ContourAttrib(
        "domain1",
        False,      # hidden
        True,       # closed
        False,      # simplified
        [1, 0, 1],  # border_color
        [1, 0, 1],  # fill_color
        11,         # fill_mode
        None,       # comment
        image_points)

    # get contours from label_dict
    contours = labels_to_contours(label_dict, pixel_size, **kwargs)

    # Assemble xml
    d = make_section_dict(section=section, image=image, image_contour=image_contour, contours=contours)
    e = dict_to_xml_str(d)
    e = prettify(e)

    return e
