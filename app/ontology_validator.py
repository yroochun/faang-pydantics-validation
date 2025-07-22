# ontology_validator.py - Django-compatible version
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import requests
from copy import deepcopy

from constants import ELIXIR_VALIDATOR_URL


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

    def resolve_schema_refs(self, schema: Dict[str, Any], base_url: str = None) -> Dict[str, Any]:
        """
        Resolve all $ref references in a JSON schema

        Args:
            schema: The schema with potential $ref references
            base_url: Base URL for resolving relative references

        Returns:
            Schema with all $ref references resolved
        """
        if base_url is None:
            # Default FAANG base URL
            base_url = "https://raw.githubusercontent.com/FAANG/dcc-metadata/master/json_schema/"

        # Deep copy to avoid modifying original
        resolved_schema = deepcopy(schema)

        def resolve_refs(obj, current_base):
            """Recursively resolve $ref in the schema"""
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]

                    # Resolve the reference
                    if ref_path.startswith("http://") or ref_path.startswith("https://"):
                        ref_url = ref_path
                    else:
                        ref_url = current_base + ref_path

                    try:
                        print(f"Resolving $ref: {ref_url}")
                        response = requests.get(ref_url, timeout=30)
                        response.raise_for_status()
                        referenced_schema = response.json()

                        # Replace the $ref with the actual schema
                        del obj["$ref"]
                        obj.update(referenced_schema)

                        # Continue resolving in the newly loaded schema
                        resolve_refs(obj, ref_url.rsplit('/', 1)[0] + '/')

                    except Exception as e:
                        print(f"Warning: Could not resolve $ref {ref_url}: {e}")
                        # Leave the $ref as is if we can't resolve it
                else:
                    # Recursively process all values
                    for key, value in obj.items():
                        resolve_refs(value, current_base)
            elif isinstance(obj, list):
                for item in obj:
                    resolve_refs(item, current_base)

        resolve_refs(resolved_schema, base_url)
        return resolved_schema

    def validate_with_elixir(self, data: Dict, schema: Dict) -> List[ValidationResult]:
        """
        Use Elixir validator for schema validation
        This matches Django's behavior - it does NOT skip graph_restriction schemas
        """
        results = []

        try:
            # First check if schema contains $ref and resolve it
            schema_str = str(schema)
            if "$ref" in schema_str:
                print("Schema contains $ref, resolving references...")
                schema = self.resolve_schema_refs(schema)

            # Django does NOT skip graph_restriction validation
            # It sends these to Elixir as well

            # Ensure schema has $schema field
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

                # Handle empty array (no errors)
                if isinstance(validation_results, list) and len(validation_results) == 0:
                    return results

                # Process errors
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
                # Django doesn't fail on Elixir errors, it just prints them
                print(f"Elixir validator returned {response.status_code}")
                # But Django still continues with validation

        except Exception as e:
            print(f"Error using Elixir validator: {e}")
            # Django continues even if Elixir fails

        return results