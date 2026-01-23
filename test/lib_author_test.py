###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.lib.author import NameIdentifierScheme, RoleTaxonomy, uri_to_identifier_schema, name_identifier_scheme_uri, check_role_in_known_taxonomy


###############################################################################
# Tests
###############################################################################
class TestAuthorMethods(unittest.TestCase):
    def test_credit_role(self):
        roles = ["conceptualization", "Data Curation", "project-administration"]
        for role in roles:
            self.assertEqual(check_role_in_known_taxonomy(role), RoleTaxonomy.CREDIT)

    def test_datacite_role(self):
        roles = ["DataCollector", "Researcher"]
        for role in roles:
            self.assertEqual(check_role_in_known_taxonomy(role), RoleTaxonomy.DATACITE)

    def test_unspecified_role(self):
        roles = ["Testing", "Misc tasks"]
        for role in roles:
            self.assertEqual(check_role_in_known_taxonomy(role), RoleTaxonomy.NONE)
