from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import pandas as pd
import argparse
import os
import threading
import time
import glob
import warnings
import shutil

from skimage.segmentation import clear_border
from skimage.measure import label, regionprops
from skimage.morphology import closing, square
from skimage.io import imread, imsave

import multiprocessing

try:  # python 2
    from annotation import xml_to_label_dict, label_dict_to_xml_str
except:  # python 3
    from .annotation import xml_to_label_dict, label_dict_to_xml_str


parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", required=True, help="path to folder containing images")
parser.add_argument("--output_dir", required=True, help="output path")
parser.add_argument("--operation", required=True, choices=["features", "contours", "labels"])
parser.add_argument("--workers", type=int, default=1, help="number of workers")
# features
parser.add_argument("--min_area", default=10, help="minimal area (in pixels) for a region to be considered for feature extraction")
# contours
parser.add_argument("--pixel_size", default=0.050, help="width of pixel in micrometer")
parser.add_argument("--section_thickness", default=0.030, help="thickness of section in micrometer")
parser.add_argument("--tolerance", type=int, default=5, help="resolution for the contours in pixels")
parser.add_argument("--level", type=int, default=254, help="value for the label (True=255)")

a = parser.parse_args()


def features(src):
    """
    Convert label image into regions and return a decription of their features.
    :param src: source image
    :return: dataframe containing the features
    """

    # apply threshold
    bw = closing(src > 0, square(3))

    # remove artifacts connected to image border
    cleared = clear_border(bw)

    # label image regions
    label_image = label(cleared)

    dst = []
    for region in regionprops(label_image):

        area = region.area

        # take regions with large enough areas
        if area >= a.min_area:

            # Features
            y0, x0 = region.centroid
            orientation = region.orientation
            length = region.major_axis_length
            width = region.minor_axis_length
            minr, minc, maxr, maxc = region.bbox

            dst.append([area, y0, x0, orientation, length, width, minr, minc, maxr, maxc])

    dst = pd.DataFrame(dst,
                       columns=['area', 'y0', 'x0', 'orientation', 'length', 'width', 'minr', 'minc', 'maxr', 'maxc'])

    return dst


def process(src_path):
    if a.operation == "features":
        """
        Extract features for registration to and save dataframe as csv file.
        """
        name, _ = os.path.splitext(os.path.basename(src_path))
        dst_path = os.path.join(a.output_dir, name + ".csv")
        src = imread(src_path)
        dst = features(src)
        dst.to_csv(dst_path)

    elif a.operation == "labels":
        """
        Convert contours (xml files) saved by Reconstruct/Win 1.1.0.1. into labels (png files).
        Note: The xml files for Reconstruct/Win 1.1.0.1 have no .xml extension,
              but  ".ser" or a dot and a digit representing the section index
        """
        name, ext = os.path.splitext(os.path.basename(src_path))
        if ext != ".ser":
            dst_basename = ext[1:]    # get rid of the leading dot
            labels, source_image = xml_to_label_dict(src_path)
            if source_image is not None:
                save_image_to_sub_dir(source_image, a.output_dir, 'image', dst_basename)
            for label_name, label_image in labels.iteritems():
                save_image_to_sub_dir(label_image, a.output_dir, label_name, dst_basename)

    elif a.operation == "contours":
        """
        Convert labels (png files) to contours (xml files) that can be read by Reconstruct/Win 1.1.0.1.
        Note: The xml files for Reconstruct/Win 1.1.0.1 have no .xml extension
        """
        image_filename = os.path.basename(src_path)
        name, _ = os.path.splitext(image_filename)
        if name.isdigit():   # filename of the image is a number string
            section_index = int(name)

            # get shape of source image and copy it to output_dir is different from input_dir
            image_shape = imread(src_path).shape
            if a.input_dir != a.output_dir:
                shutil.copyfile(src_path, os.path.join(a.output_dir, image_filename))

            # get label images from label directories and use directory name as label name
            label_dict = dict()
            for label_name, label_dir in label_dirs.iteritems():
                label_filename = os.path.join(label_dir, name + ".png")
                if os.path.exists(label_filename):
                    label_image = imread(label_filename)
                    label_dict[label_name] = label_image
                # else:
                #     print ("No label %s for section %d" % (label_name, section_index))

            # xml file with contours
            e = label_dict_to_xml_str(
                label_dict=label_dict,
                image_shape=image_shape,
                image_filename=image_filename,
                pixel_size=float(a.pixel_size),
                section_thickness=float(a.section_thickness),
                section_index=int(name),
                tolerance=int(a.tolerance),
                level=int(a.level))
            # xml_filename = os.path.join(a.output_dir, 'series'+name+".xml")
            xml_filename = os.path.join(a.output_dir, 'series.'+name)   # no xml extension used !
            with open(xml_filename, "w") as text_file:
                text_file.write(e)

    else:
        raise Exception("invalid operation")


def save_image_to_sub_dir(image, base_dir, sub_dir, basename, ext=".png"):
    full_dir = os.path.join(base_dir, sub_dir)
    if not os.path.exists(full_dir):
        os.makedirs(full_dir)
    full_path = os.path.join(full_dir, basename+ext)
    with warnings.catch_warnings():  # suppress "low contrast image" warning while saving 16bit png with labels
        warnings.simplefilter("ignore")
        imsave (full_path, image)


complete_lock = threading.Lock()
start = None
num_complete = 0
total = 0

def complete():
    global num_complete, rate, last_complete

    num_complete += 1
    now = time.time()
    elapsed = now - start
    rate = num_complete / elapsed
    if rate > 0:
        remaining = (total - num_complete) / rate
    else:
        remaining = 0

    print("%d/%d complete  %0.2f images/sec  %dm%ds elapsed  %dm%ds remaining" % (num_complete, total, rate, elapsed // 60, elapsed % 60, remaining // 60, remaining % 60))

    last_complete = now


def main():
    if not os.path.exists(a.output_dir):
        os.makedirs(a.output_dir)

    if a.operation == 'contours':
        global label_dirs
        label_dirs = dict()
        image_dir = os.path.dirname(a.input_dir)
        parent_dir = os.path.dirname(os.path.dirname(a.input_dir))
        for sub_dir in os.listdir(parent_dir):
            abs_path = os.path.join(parent_dir, sub_dir)
            if os.path.isdir(abs_path) and abs_path != image_dir:
                label_dirs[sub_dir] = abs_path
        print ('(Presumed) labels:', label_dirs.keys())
        # TODO: Make a series.xml file with the name "*.ser"


    # Get all files if input_dir contains a wildcard
    if "*" in a.input_dir[-1]:
        src_paths = glob.glob(a.input_dir)
    # Get all files within the directory input_dir, or all files that start with input_dir
    # Note: if input_dir is a directory adding a "*" will get all files within this directory without recursion
    else:
        src_paths = glob.glob(a.input_dir+"*")

    global total
    total = len(src_paths)
    
    print("processing %d files" % total)

    global start
    start = time.time()

    if a.workers == 1:
        for args in src_paths:
            process(args)
            complete()
    else:
        pool = multiprocessing.Pool(a.workers)
        for result in pool.imap_unordered(process, src_paths):
            complete()

main()
