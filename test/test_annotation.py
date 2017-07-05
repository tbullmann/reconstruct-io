from io import StringIO
from unittest import TestCase

from annotation import *

# Print results on console or make figures with matplotlib
from pprint import pprint
from matplotlib import pyplot as plt
from skimage.color import label2rgb


SHOW_RESULTS = False
EXAMPLE_SECTION_FILENAME = os.path.dirname(__file__) + '/xml_example/newSeries.373.xml'
EXAMPLE_IMAGE_FILENAME = os.path.dirname(__file__) + '/xml_example/image0373_(monitor126).bmp.tif'
EXAMPLE_SERIES_FILENAME = os.path.dirname(__file__) + '/xml_example/newSeries.ser.xml'

class TestVerify(TestCase):
    def test_verify_section_xml(self):
        self.assertEqual(verify(EXAMPLE_SECTION_FILENAME, SECTION_DTD_FILENAME), True)

    def test_verify_series_xml(self):
        self.assertEqual(verify(EXAMPLE_SERIES_FILENAME, SERIES_DTD_FILENAME), True)


class TestXMLIO(TestCase):

    def test_simple_XML(self):
        """
        Test etree_to_dict and dict_to_xml_str using a simple xml file (see reference in function description).
        """

        e = ET.XML('''
        <root>
          <e />
          <e>text</e>
          <e name="value" />
          <e name="value">text</e>
          <e> <a>text</a> <b>text</b> </e>
          <e> <a>text</a> <a>text</a> </e>
          <e> text <a>text</a> </e>
        </root>
        ''')

        d = etree_to_dict(e)

        if SHOW_RESULTS:
            pprint(d)

        e = dict_to_xml_str(d)

        if SHOW_RESULTS:
            print(e)
            print(prettify(e))

    def test_xml_to_dict_and_back(self):
        """
        Convert example section xml to dict. Then reconstruct the xml and verify the new xml using SECTION.XML
        """
        # etree_to_dict(e) and dict_to_etree(d)
        e = open(EXAMPLE_SECTION_FILENAME, 'r').read()
        e = ET.XML(e)
        d = etree_to_dict(e)

        if SHOW_RESULTS:
            print(d)

        e = dict_to_xml_str(d)
        e = prettify(e)

        if SHOW_RESULTS:
            print(e)

        xml_file = StringIO(unicode(e))
        self.assertEqual(verify_files(xml_file, open(SECTION_DTD_FILENAME, 'r')), True)

    def test_xml_from_dict(self):
        """
        Make a xml from default attributes for sections, transforms, contours and verify the new xml using SECTION.XML
        """
        d = make_section_dict()   # using default values
        e = dict_to_xml_str(d)
        e = prettify(e)

        if SHOW_RESULTS:
            print(e)

        xml_file = StringIO(unicode(e))
        self.assertTrue(verify_files(xml_file, open(SECTION_DTD_FILENAME, 'r')))

    def test_xml_to_attributes_and_back(self):
        """
        Convert example section xml to attributes of sections, transforms, contours, ...
        Then reconstruct the xml and verify the new xml using SECTION.XML
        """
        # etree_to_dict(e) and dict_to_etree(d)
        e = open(EXAMPLE_SECTION_FILENAME, 'r').read()
        e = ET.XML(e)
        d = etree_to_dict(e)
        all_attributes = read_section_dict(d)
        d = make_section_dict(*all_attributes)
        e = dict_to_xml_str(d)
        e = prettify(e)

        if SHOW_RESULTS:
            print(e)

        xml_file = StringIO(unicode(e))
        self.assertEqual(verify_files(xml_file, open(SECTION_DTD_FILENAME, 'r')), True)


class TestPNGIO(TestCase):

    def test_xml_to_label_dict(self):
        xml_filename = EXAMPLE_SECTION_FILENAME

        labels, source_image = xml_to_label_dict(xml_filename)

        if SHOW_RESULTS:
            image_label = labels.itervalues().next()  # for testing access a random label
            image_label_overlay = label2rgb(image_label, source_image)

            plt.imshow(image_label_overlay)
            plt.show()

        self.assertTrue('dendrite1' in labels.keys())

    def make_example_label_dict_for_testing(self, image_filename):
        # create dict of labels
        source_image = imread(image_filename)
        from skimage.morphology import disk
        from skimage.filters import rank
        image = source_image.copy()
        selem = disk(20)
        bilateral_result = rank.mean_bilateral(image, selem=selem, s0=500, s1=500)   # a little smooting
        image_label = bilateral_result < 128   # threshold dark parts, that is the example precipitate
        label_dict = {'dendrite': image_label}   # only one label type
        return label_dict, image_label, source_image

    def test_label_dict_to_xml(self):
        pixel_size = 0.005
        labels, image_label, source_image = self.make_example_label_dict_for_testing(EXAMPLE_IMAGE_FILENAME)

        # iterator through labels
        contours = labels_to_contours(labels, pixel_size)


        if SHOW_RESULTS:
            image_label_overlay = label2rgb(image_label, source_image)
            plt.imshow(image_label_overlay)
            for contour in contours:
                points = contour.points / pixel_size
                plt.plot(points[:, 1], points[:, 0], '-r', linewidth=2)
                print ("Contour %s with %d points." % (contour.name, len(contour.points)))
            plt.show()

        self.assertEqual(len(contours), 8)

    def test_label_dict_to_xml_str(self):
        image_filename = EXAMPLE_IMAGE_FILENAME
        label_dict, _, source_image = self.make_example_label_dict_for_testing(image_filename)
        xml_filename = os.path.join(os.path.dirname(image_filename), 'test.xml')

        # create list of contours from label_dict
        e = label_dict_to_xml_str(label_dict=label_dict,
                                  image_shape=source_image.shape,
                                  image_filename=os.path.basename(image_filename),
                                  pixel_size=0.005,
                                  section_thickness=0.012,
                                  section_index=373)

        # if SHOW_RESULTS:
        print(e)

        xml_file = StringIO(unicode(e))
        self.assertEqual(verify_files(xml_file, open(SECTION_DTD_FILENAME, 'r')), True)


# TODO: Empty contour list

# TODO: # Include the DCOTYPE in the second line of the XML
# <!DOCTYPE Section SYSTEM "section.dtd">


# TODO (5) SERIES.XML import/export
# Guess thats needed too

