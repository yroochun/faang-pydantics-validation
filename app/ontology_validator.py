from typing import List, Dict, Any
from pydantic import BaseModel, Field
import requests

from constants import ELIXIR_VALIDATOR_URL


class ValidationResult(BaseModel):
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    field_path: str
    value: Any = None


class OntologyValidator:
    def __init__(self, cache_enabled: bool = True):
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, Any] = {}

    def validate_ontology_term(self, term: str, ontology_name: str,
                               allowed_classes: List[str],
                               text: str = None) -> ValidationResult:

        result = ValidationResult(field_path=f"{ontology_name}:{term}")

        if term == "restricted access":
            return result

        # check OLS for term and text validity
        ols_data = self.fetch_from_ols(term)
        if not ols_data:
            result.errors.append(f"Term {term} not found in OLS")
            return result

        if text:
            ols_labels = [doc.get('label', '').lower() for doc in ols_data
                          if doc.get('ontology_name', '').lower() == ontology_name.lower()]

            if not ols_labels:
                ols_labels = [doc.get('label', '').lower() for doc in ols_data]

            if text.lower() not in ols_labels:
                expected_label = ols_labels[0] if ols_labels else "unknown"
                result.warnings.append(
                    f"Provided value '{text}' doesn't precisely match '{expected_label}' "
                    f"for term '{term}'"
                )

        return result

    def fetch_from_ols(self, term_id: str) -> List[Dict]:
        if self.cache_enabled and term_id in self._cache:
            return self._cache[term_id]

        try:
            url = f"http://www.ebi.ac.uk/ols/api/search?q={term_id.replace(':', '_')}&rows=100"
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
        results = []

        try:
            if "$schema" not in schema:
                schema = schema.copy()
                schema["$schema"] = "http://json-schema.org/draft-07/schema#"

            json_to_send = {
                'schema': schema,
                'object': data
            }

            response = requests.post(ELIXIR_VALIDATOR_URL, json=json_to_send, timeout=30)

            if response.status_code == 200:
                validation_results = response.json()

                # empty array
                if isinstance(validation_results, list) and len(validation_results) == 0:
                    return results

                for item in validation_results:
                    if isinstance(item, dict) and item.get('errors'):
                        errors = [e for e in item['errors']
                                  if e != 'should match exactly one schema in oneOf']
                        if errors:
                            result = ValidationResult(
                                field_path=item.get('dataPath', '') or item.get('instancePath', ''),
                                errors=errors
                            )
                            results.append(result)
            else:
                print(f"Elixir validator returned {response.status_code}")

        except Exception as e:
            print(f"Error using Elixir validator: {e}")

        return results