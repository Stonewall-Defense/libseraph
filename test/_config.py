###############################################################################
# Global Imports
###############################################################################
from typing import Optional


###############################################################################
# Constants
###############################################################################
TEST_DATASET_ALPHA = "test/res/component_alpha"
TEST_DATASET_BETA = "test/res/component_beta"

SERAPH_FILE_CONTENTS = {
    "uri": "tag:certusinnovations.com,2024:datasets:ExampleFileContents",
    "version": "v0.0.0",
    "name": "Example File Contents",
    "authors": [
        {
            "uri": "tag:certusinnovations.com,2024:agents:RyanQuinn",
            "name": "Ryan Quinn",
            "roles": [
                "associatedWith"
            ],
            "givenName": None,
            "familyName": None,
            "identifierScheme": "tag",
            "email": None,
            "affiliations": [
                {
                    "uri": "https://ror.org/test-org",
                    "name": "Test org",
                    "address": None,
                    "identifierScheme": "ROR",
                }
            ]
        }
    ],
    "keywords": [],
    "creationDate": "2026-01-23T13:27:00Z",
    "mediaType": "audio",
    "mediaSubtype": "wav",
    "license": "https://opensource.org/licenses/MIT",
}


###############################################################################
# Utility Classes
###############################################################################
class MockInput:
    # See https://dnmtechs.com/mocking-user-input-for-unit-testing-in-python-3/

    def __init__(self, values: list[str]):
        self.values = values
        self.index = 0

    def __call__(self, prompt: Optional[str] = None):
        value = self.values[self.index]
        self.index += 1
        return value
