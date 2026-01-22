###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.lib.license import LicenseStatus, LicenseConformance, load_license, _format_license_concerns


###############################################################################
# Tests
###############################################################################
class TestLicenseMethods(unittest.TestCase):
    def test_unknown_license(self):
        id = "tag:certusinnovations.com,2024:license:restricted"
        license = load_license(id)
        self.assertIsNone(license)

    def test_osd_license(self):
        id = "Apache-1.1"
        license = load_license(id)
        if license is None:
            raise ValueError(id)

        self.assertEqual(license.id, id)
        self.assertTrue(license.is_of_concern)
        self.assertEqual(license.osd_conformance, LicenseConformance.APPROVED)
        self.assertEqual(license.od_conformance, LicenseConformance.NOT_REVIEWED)
        self.assertEqual(license.status, LicenseStatus.RETIRED)
        self.assertEqual(license.url, "https://opensource.org/licenses/Apache-1.1")

    def test_od_license(self):
        id = "https://opendefinition.org/licenses/against-drm"
        license = load_license(id)
        if license is None:
            raise ValueError(id)

        self.assertEqual(license.id, "Against-DRM")
        self.assertTrue(license.is_of_concern)
        self.assertEqual(license.osd_conformance, LicenseConformance.NOT_REVIEWED)
        self.assertEqual(license.od_conformance, LicenseConformance.APPROVED)
        self.assertEqual(license.status, LicenseStatus.ACTIVE)
        self.assertEqual(license.url, id)

    def test_no_concerns(self):
        id = "MirOS"
        license = load_license(id)
        if license is None:
            raise ValueError(id)

        self.assertEqual(license.id, id)
        self.assertFalse(license.is_of_concern)
        self.assertEqual(license.osd_conformance, LicenseConformance.APPROVED)
        self.assertEqual(license.od_conformance, LicenseConformance.APPROVED)
        self.assertEqual(license.status, LicenseStatus.ACTIVE)
        self.assertEqual(license.url, "https://opensource.org/licenses/MirOS")

    def test_fmt_no_license(self):
        id = "tag:certusinnovations.com,2024:license:restricted"
        license = load_license(id)
        fmt = _format_license_concerns(license)
        self.assertEqual(fmt, "[yellow]WARNING: That license is not registered with https://opendefinition.org/[/yellow]")

    def test_fmt_concerns(self):
        id = "https://opendefinition.org/licenses/dsl"
        license = load_license(id)
        fmt = _format_license_concerns(license)
        expected = " > Possible license concerns: OSI conformance is [yellow]NOT REVIEWED[/yellow]"
        self.assertEqual(fmt, expected)

    def test_fmt_concerns_retired(self):
        id = "EPL-1.0"
        license = load_license(id)
        fmt = _format_license_concerns(license)
        expected = " > Possible license concerns: Open Definition conformance is [yellow]NOT REVIEWED[/yellow], license status is [red]RETIRED[/red]"
        self.assertEqual(fmt, expected)
