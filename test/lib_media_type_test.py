###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.lib.media_type import SupportedMediaType, MediaTypeTree, check_media_type


###############################################################################
# Tests
###############################################################################
class TestMediaTypeMethods(unittest.TestCase):
    def test_pathological(self):
        media_type = "pathological"
        with self.assertRaises(ValueError):
            check_media_type(media_type)

    def test_multimedia_ok(self):
        media_type = "multimedia"
        fmt_type, fmt_sub = check_media_type(media_type)
        self.assertEqual(fmt_type, SupportedMediaType.MULTIMEDIA)
        self.assertIsNone(fmt_sub)

    def test_multimedia_bad(self):
        media_type = "multimedia/subtype"
        with self.assertRaises(ValueError):
            check_media_type(media_type)

    def test_ok_no_subtype(self):
        media_type = "audio"
        fmt_type, fmt_sub = check_media_type(media_type)
        self.assertEqual(fmt_type, SupportedMediaType.AUDIO)
        self.assertIsNone(fmt_sub)

    def test_ok_with_subtype(self):
        media_type = "audio/wav"
        fmt_type, fmt_sub = check_media_type(media_type)
        self.assertEqual(fmt_type, SupportedMediaType.AUDIO)
        self.assertEqual(fmt_sub, "wav")

    def test_ok_separate_subtype(self):
        media_type, subtype = "video", "H263-2000"
        fmt_type, fmt_sub = check_media_type(media_type, subtype)
        self.assertEqual(fmt_type, SupportedMediaType.VIDEO)
        self.assertEqual(fmt_sub, "H263-2000")

    def test_fail_with_subtype(self):
        media_type = "audio/bad"
        with self.assertRaises(ValueError):
            check_media_type(media_type)

    def test_fail_separate_subtype(self):
        media_type, subtype = "video", "wav"
        with self.assertRaises(ValueError):
            check_media_type(media_type, subtype)

    def test_ok_tree(self):
        media_type = "text/vnd.dvb.subtitle"
        fmt_type, fmt_sub = check_media_type(media_type)
        self.assertEqual(fmt_type, SupportedMediaType.TEXT)
        self.assertEqual(fmt_sub, "vnd.dvb.subtitle")

    def test_fail_tree(self):
        media_type = "image/prs.btif"
        with self.assertRaises(ValueError):
            check_media_type(media_type)

    def test_additional_tree(self):
        media_type = "text/prs.fallenstein.rst"
        fmt_type, fmt_sub = check_media_type(media_type, allowed_media_type_trees=[MediaTypeTree.PRS])
        self.assertEqual(fmt_type, SupportedMediaType.TEXT)
        self.assertEqual(fmt_sub, "prs.fallenstein.rst")

    def test_fail_3_parts(self):
        media_type = "image/image/image"
        with self.assertRaises(ValueError):
            check_media_type(media_type)

    def test_fail_two_subtypes(self):
        media_type, subtype = "image/jpeg", "png"
        with self.assertRaises(ValueError):
            check_media_type(media_type, subtype)
