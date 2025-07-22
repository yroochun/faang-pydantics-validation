from typing import List, Optional
from pydantic import BaseModel, Field, validator, root_validator, ValidationError
from typing import List, Optional, Union, Dict, Any, Tuple, Set
import requests

# Import constants from your constants file
from constants import (
    SPECIES_BREED_LINKS, MISSING_VALUES, ALLOWED_RELATIONSHIPS,
    SKIP_PROPERTIES, ORGANISM_URL, SAMPLE_CORE_URL,
    ELIXIR_VALIDATOR_URL, ALLOWED_SAMPLES_TYPES
)

class ValidationResult(BaseModel):
    """Container for validation results with errors and warnings"""
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    field_path: str
    value: Any = None

class OntologyValidator:
    """Handles ontology validation and OLS lookups"""

    def __init__(self, cache_enabled: bool = True):
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, Any] = {}

    def validate_ontology_term(self, term: str, ontology_name: str,
                               allowed_classes: List[str],
                               text: str = None) -> ValidationResult:
        """Validate ontology term against allowed classes and check text consistency"""
        result = ValidationResult(field_path=f"{ontology_name}:{term}")

        if term == "restricted access":
            return result

        # Check OLS for term validity and text consistency
        ols_data = self._fetch_from_ols(term)
        if not ols_data:
            result.errors.append(f"Term {term} not found in OLS")
            return result

        # Validate text matches OLS label
        if text:
            ols_labels = [doc.get('label', '').lower() for doc in ols_data
                          if doc.get('ontology_name', '').lower() == ontology_name.lower()]

            if not ols_labels:
                # Try without ontology name filter
                ols_labels = [doc.get('label', '').lower() for doc in ols_data]

            if text.lower() not in ols_labels:
                expected_label = ols_labels[0] if ols_labels else "unknown"
                result.warnings.append(
                    f"Provided value '{text}' doesn't precisely match '{expected_label}' "
                    f"for term '{term}'"
                )

        return result

    def _fetch_from_ols(self, term_id: str) -> List[Dict]:
        """Fetch term data from OLS API"""
        if self.cache_enabled and term_id in self._cache:
            return self._cache[term_id]

        try:
            url = f"http://www.ebi.ac.uk/ols/api/search?q={term_id.replace(':', '_')}&rows=100"
            print(url)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            docs = data.get('response', {}).get('docs', [])
            if self.cache_enabled:
                self._cache[term_id] = docs
            return docs
        except Exception as e:
            print(f"Error fetching from OLS: {e}")
            return []

    def validate_with_elixir(self, data: Dict, schema: Dict) -> List[ValidationResult]:
        """Use Elixir validator for schema validation"""
        results = []

        try:
            json_to_send = {
                'schema': schema,
                'object': data
            }
            response = requests.post(ELIXIR_VALIDATOR_URL, json=json_to_send, timeout=30)
            response.raise_for_status()
            validation_results = response.json()

            for item in validation_results:
                if item.get('errors'):
                    errors = [e for e in item['errors']
                              if e != 'should match exactly one schema in oneOf']
                    if errors:
                        result = ValidationResult(
                            field_path=item.get('dataPath', ''),
                            errors=errors
                        )
                        results.append(result)
        except Exception as e:
            print(f"Error using Elixir validator: {e}")

        return results