# breed_species_validator.py
"""
Breed-species validation matching Django's implementation
"""

from typing import Dict, Any, List
from constants import SPECIES_BREED_LINKS


class BreedSpeciesValidator:
    """Validates breed against species using graph restrictions like Django"""

    def __init__(self, ontology_validator):
        self.ontology_validator = ontology_validator

    def validate_breed_for_species(self, organism_term: str, breed_term: str) -> List[str]:
        """
        Validate breed is appropriate for species using Elixir validator
        This matches Django's WarningsAndAdditionalChecks.check_breeds method
        """
        errors = []

        if organism_term not in SPECIES_BREED_LINKS:
            # No breed restrictions for this species
            return errors

        if breed_term in ["not applicable", "restricted access"]:
            return errors

        # Create schema for breed validation - exactly like Django
        breed_schema = {
            "type": "string",
            "graph_restriction": {
                "ontologies": ["obo:lbo"],
                "classes": [SPECIES_BREED_LINKS[organism_term]],
                "relations": ["rdfs:subClassOf"],
                "direct": False,
                "include_self": True
            }
        }

        # Validate with Elixir - Django sends the term string, not the full object
        validation_results = self.ontology_validator.validate_with_elixir(breed_term, breed_schema)

        if validation_results:
            # Has errors - breed doesn't match species
            errors.append("Breed doesn't match the animal species")

        return errors