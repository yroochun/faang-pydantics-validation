# organism_validation.py
"""
Enhanced organism validation using Pydantic to replace Django validation logic.
This module consolidates schema validation, additional checks, and relationship validation.
"""

from pydantic import BaseModel, Field, validator, root_validator, ValidationError
from typing import List, Optional, Union, Dict, Any, Tuple, Set
from enum import Enum
import re
from datetime import datetime
import requests
from collections import defaultdict
import json

# Import your existing models
from organism_ruleset import (
    FAANGOrganismSample, Organism, Sex, BirthDate, Breed, HealthStatus,
    DateUnits, WeightUnits, TimeUnits, DeliveryTiming, DeliveryEase,
    BaseOntologyTerm, SampleCoreMetadata
)

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


class ValidationDocument(BaseModel):
    """Document structure for validation results matching Django output format"""
    organism: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        extra = "allow"


class SchemaCache:
    """Cache for JSON schemas to avoid repeated downloads"""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get_schema(self, url: str) -> Dict[str, Any]:
        """Get schema from cache or download it"""
        if url not in self._cache:
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                self._cache[url] = response.json()
            except Exception as e:
                print(f"Error fetching schema from {url}: {e}")
                return {}
        return self._cache[url]


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


class RelationshipValidator:
    """Handles organism relationship validation"""

    def __init__(self):
        self.biosamples_cache: Dict[str, Dict] = {}

    def validate_relationships(self,
                               organisms: List[Dict[str, Any]],
                               action: str = 'new') -> Dict[str, ValidationResult]:
        """Validate parent-child relationships between organisms"""
        results = {}

        # Build a map of organism names to their data
        organism_map = {}
        for org in organisms:
            name = self._get_organism_identifier(org, action)
            organism_map[name] = org

        # Fetch BioSamples data if needed
        biosample_ids = set()
        for org in organisms:
            child_of = org.get('child_of', [])
            if isinstance(child_of, dict):
                child_of = [child_of]
            for parent in child_of:
                parent_id = parent.get('value', '')
                if parent_id.startswith('SAM'):
                    biosample_ids.add(parent_id)

        if biosample_ids:
            self._fetch_biosample_data(list(biosample_ids))

        # Validate each organism's relationships
        for org in organisms:
            name = self._get_organism_identifier(org, action)
            result = ValidationResult(field_path=f"organism.{name}.child_of")

            child_of = org.get('child_of', [])
            if isinstance(child_of, dict):
                child_of = [child_of]

            for parent_ref in child_of:
                parent_id = parent_ref.get('value', '')

                # Skip validation for special values
                if parent_id == 'restricted access':
                    continue

                # Check if parent exists
                if parent_id not in organism_map and parent_id not in self.biosamples_cache:
                    result.errors.append(
                        f"Relationships part: no entity '{parent_id}' found"
                    )
                    continue

                # Get parent data
                if parent_id in organism_map:
                    parent_data = organism_map[parent_id]
                    parent_species = parent_data.get('organism', {}).get('text', '')
                    parent_material = 'organism'
                else:
                    parent_data = self.biosamples_cache.get(parent_id, {})
                    parent_species = parent_data.get('organism', '')
                    parent_material = parent_data.get('material', '').lower()

                # Validate species match
                current_species = org.get('organism', {}).get('text', '')

                if current_species and parent_species and current_species != parent_species:
                    result.errors.append(
                        f"Relationships part: the specie of the child '{current_species}' "
                        f"doesn't match the specie of the parent '{parent_species}'"
                    )

                # Check material type is allowed
                allowed_materials = ALLOWED_RELATIONSHIPS.get('organism', [])
                if parent_material and parent_material not in allowed_materials:
                    result.errors.append(
                        f"Relationships part: referenced entity '{parent_id}' "
                        f"does not match condition 'should be {' or '.join(allowed_materials)}'"
                    )

                # Check for circular relationships
                if parent_id in organism_map:
                    parent_relationships = parent_data.get('child_of', [])
                    if isinstance(parent_relationships, dict):
                        parent_relationships = [parent_relationships]

                    for grandparent in parent_relationships:
                        if grandparent.get('value') == name:
                            result.errors.append(
                                f"Relationships part: parent '{parent_id}' "
                                f"is listing the child as its parent"
                            )

            if result.errors or result.warnings:
                results[name] = result

        return results

    def _get_organism_identifier(self, organism: Dict, action: str = 'new') -> str:
        """Get the identifier for an organism based on action type"""
        col_name = 'biosample_id' if action == 'update' else 'sample_name'

        if 'custom' in organism and col_name in organism['custom']:
            return organism['custom'][col_name]['value']
        elif 'alias' in organism:
            return organism.get('alias', {}).get('value', 'unknown')

        return 'unknown'

    def _fetch_biosample_data(self, biosample_ids: List[str]):
        """Fetch data for BioSample IDs"""
        for sample_id in biosample_ids:
            if sample_id in self.biosamples_cache:
                continue

            try:
                url = f"https://www.ebi.ac.uk/biosamples/samples/{sample_id}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()

                    # Extract relevant data
                    cache_entry = {}

                    # Get organism
                    characteristics = data.get('characteristics', {})
                    if 'organism' in characteristics:
                        cache_entry['organism'] = characteristics['organism'][0].get('text', '')

                    # Get material
                    if 'material' in characteristics:
                        cache_entry['material'] = characteristics['material'][0].get('text', '')

                    # Get relationships
                    relationships = []
                    for rel in data.get('relationships', []):
                        if rel['source'] == sample_id and rel['type'] in ['child of', 'derived from']:
                            relationships.append(rel['target'])
                    cache_entry['relationships'] = relationships

                    self.biosamples_cache[sample_id] = cache_entry
            except Exception as e:
                print(f"Error fetching BioSample {sample_id}: {e}")


class EnhancedFAANGOrganismValidator:
    """Main validator class that combines all validation logic"""

    def __init__(self):
        self.ontology_validator = OntologyValidator()
        self.relationship_validator = RelationshipValidator()
        self.schema_cache = SchemaCache()

        # Load schemas
        self.organism_schema = self.schema_cache.get_schema(ORGANISM_URL)
        self.samples_core_schema = self.schema_cache.get_schema(SAMPLE_CORE_URL)

        # Extract field requirements from schemas
        self.field_requirements = self._extract_field_requirements()
        self.ontology_names = self._extract_ontology_names()

    def validate_organism_sample(self, data: Dict[str, Any],
                                 check_relationships: bool = True,
                                 check_ontologies: bool = True,
                                 action: str = 'new') -> Tuple[Optional[FAANGOrganismSample], List[ValidationResult]]:
        """
        Validate a single organism sample with all checks

        Returns:
            Tuple of (validated_model, validation_results)
        """
        all_results = []

        # First, try basic Pydantic validation
        try:
            organism_model = FAANGOrganismSample(**data)
        except ValidationError as e:
            # Convert Pydantic errors to ValidationResult
            for error in e.errors():
                result = ValidationResult(
                    field_path='.'.join(str(x) for x in error['loc']),
                    errors=[error['msg']],
                    value=error.get('input')
                )
                all_results.append(result)
            return None, all_results

        # Use Elixir validator for additional schema validation
        if self.organism_schema:
            elixir_results = self.ontology_validator.validate_with_elixir(
                data, self.organism_schema
            )
            all_results.extend(elixir_results)

        # Additional validations beyond basic schema

        # 1. Check recommended fields
        for field in self.field_requirements['recommended']['type']:
            if field not in data or data[field] is None:
                result = ValidationResult(
                    field_path=field,
                    warnings=['This item is recommended but was not provided']
                )
                all_results.append(result)

        # Check core recommended fields
        if 'samples_core' in data:
            for field in self.field_requirements['recommended']['core']:
                if field not in data['samples_core'] or data['samples_core'][field] is None:
                    result = ValidationResult(
                        field_path=f"samples_core.{field}",
                        warnings=['This item is recommended but was not provided']
                    )
                    all_results.append(result)

        # 2. Validate breed-species consistency
        if organism_model.breed and organism_model.organism:
            breed_result = self._validate_breed_species_consistency(
                organism_model.organism,
                organism_model.breed
            )
            if breed_result.errors or breed_result.warnings:
                all_results.append(breed_result)

        # 3. Validate date consistency
        if organism_model.birth_date:
            date_result = self._validate_date_consistency(organism_model.birth_date)
            if date_result.errors:
                all_results.append(date_result)

        # 4. Check for inappropriate missing values
        missing_value_results = self._check_missing_values(data)
        all_results.extend(missing_value_results)

        # 5. Ontology validation
        if check_ontologies:
            ontology_results = self._validate_ontologies(data)
            all_results.extend(ontology_results)

        # 6. Check custom fields
        if 'custom' in data:
            custom_results = self._validate_custom_fields(data['custom'])
            all_results.extend(custom_results)

        return organism_model, all_results

    def validate_organism_batch(self, organisms: List[Dict[str, Any]],
                                structure: Dict[str, Any],
                                action: str = 'new',
                                check_relationships: bool = True) -> Dict[str, Any]:
        """
        Validate a batch of organisms with relationship checking

        Returns:
            Dictionary with validation results matching Django format
        """
        validation_document = {'organism': []}

        # First pass: validate individual organisms
        for i, org_data in enumerate(organisms):
            organism_id = self._get_organism_identifier(org_data, action)
            if not organism_id:
                organism_id = f"organism_{i + 1}"

            # Create record structure matching Django format
            record_structure = self._get_record_structure(
                structure.get('organism', {}),
                org_data,
                organism_id,
                action
            )

            # Validate the organism
            model, validation_results = self.validate_organism_sample(
                org_data,
                check_relationships=False,
                action=action
            )

            # Apply validation results to the record structure
            for result in validation_results:
                self._apply_validation_result_to_structure(
                    record_structure, result
                )

            validation_document['organism'].append(record_structure)

        # Second pass: validate relationships
        if check_relationships:
            relationship_results = self.relationship_validator.validate_relationships(
                organisms, action
            )

            # Apply relationship results to the document
            for org_id, rel_result in relationship_results.items():
                # Find the corresponding record
                for record in validation_document['organism']:
                    col_name = 'biosample_id' if action == 'update' else 'sample_name'
                    if record['custom'].get(col_name, {}).get('value') == org_id:
                        # Apply relationship errors
                        if 'child_of' in record:
                            if isinstance(record['child_of'], list):
                                for child_ref in record['child_of']:
                                    child_ref.setdefault('errors', [])
                                    child_ref['errors'].extend(rel_result.errors)
                            else:
                                record['child_of'].setdefault('errors', [])
                                record['child_of']['errors'].extend(rel_result.errors)
                        break

        return validation_document

    def _extract_field_requirements(self) -> Dict[str, Dict[str, List[str]]]:
        """Extract mandatory, recommended, and optional fields from schemas"""
        requirements = {
            'mandatory': {'core': [], 'type': []},
            'recommended': {'core': [], 'type': []},
            'optional': {'core': [], 'type': []}
        }

        # Extract from organism schema
        if self.organism_schema and 'properties' in self.organism_schema:
            for field_name, field_def in self.organism_schema['properties'].items():
                if field_name not in SKIP_PROPERTIES:
                    requirement = self._get_field_requirement(field_def)
                    if requirement:
                        requirements[requirement]['type'].append(field_name)

        # Extract from core schema
        if self.samples_core_schema and 'properties' in self.samples_core_schema:
            for field_name, field_def in self.samples_core_schema['properties'].items():
                if field_name not in SKIP_PROPERTIES:
                    requirement = self._get_field_requirement(field_def)
                    if requirement:
                        requirements[requirement]['core'].append(field_name)

        return requirements

    def _get_field_requirement(self, field_def: Dict) -> Optional[str]:
        """Get the requirement level of a field from its definition"""
        if field_def.get('type') == 'object':
            mandatory = field_def.get('properties', {}).get('mandatory', {}).get('const')
            if mandatory:
                return mandatory
        elif field_def.get('type') == 'array':
            mandatory = field_def.get('items', {}).get('properties', {}).get('mandatory', {}).get('const')
            if mandatory:
                return mandatory
        return None

    def _extract_ontology_names(self) -> Dict[str, List[str]]:
        """Extract expected ontology names for each field"""
        ontology_names = {}

        if self.organism_schema and 'properties' in self.organism_schema:
            for field_name, field_def in self.organism_schema['properties'].items():
                if field_name not in SKIP_PROPERTIES:
                    onto_names = self._get_ontology_names_from_field(field_def)
                    if onto_names:
                        ontology_names[field_name] = onto_names

        return ontology_names

    def _get_ontology_names_from_field(self, field_def: Dict) -> List[str]:
        """Extract ontology names from field definition"""
        onto_names = []

        if field_def.get('type') == 'object':
            props = field_def.get('properties', {})
            if 'ontology_name' in props:
                if 'const' in props['ontology_name']:
                    onto_names.append(props['ontology_name']['const'].lower())
                elif 'enum' in props['ontology_name']:
                    onto_names.extend([n.lower() for n in props['ontology_name']['enum']])
        elif field_def.get('type') == 'array':
            items_props = field_def.get('items', {}).get('properties', {})
            if 'ontology_name' in items_props:
                if 'const' in items_props['ontology_name']:
                    onto_names.append(items_props['ontology_name']['const'].lower())
                elif 'enum' in items_props['ontology_name']:
                    onto_names.extend([n.lower() for n in items_props['ontology_name']['enum']])

        return onto_names

    def _validate_breed_species_consistency(self, organism: Organism,
                                            breed: Breed) -> ValidationResult:
        """Validate that breed is appropriate for the species"""
        result = ValidationResult(field_path="organism")

        if organism.term not in SPECIES_BREED_LINKS:
            # Species doesn't have breed restrictions
            return result

        expected_breed_class = SPECIES_BREED_LINKS[organism.term]

        # Use Elixir validator to check breed against species
        breed_schema = {
            "type": "string",
            "graph_restriction": {
                "ontologies": ["obo:lbo"],
                "classes": [expected_breed_class],
                "relations": ["rdfs:subClassOf"],
                "direct": False,
                "include_self": True
            }
        }

        validation_results = self.ontology_validator.validate_with_elixir(
            breed.term, breed_schema
        )

        if validation_results:
            result.errors.append(
                f"Breed '{breed.text}' doesn't match the animal specie: '{organism.text}'"
            )

        return result

    def _validate_date_consistency(self, birth_date: BirthDate) -> ValidationResult:
        """Validate date format matches the units"""
        result = ValidationResult(field_path="birth_date")

        if birth_date.value in ["not applicable", "not collected", "not provided", "restricted access"]:
            return result

        format_map = {
            DateUnits.YYYY_MM_DD: '%Y-%m-%d',
            DateUnits.YYYY_MM: '%Y-%m',
            DateUnits.YYYY: '%Y'
        }

        expected_format = format_map.get(birth_date.units)
        if expected_format:
            try:
                datetime.strptime(birth_date.value, expected_format)
            except ValueError:
                result.errors.append(
                    f"Date units: {birth_date.units} should be consistent with "
                    f"date value: {birth_date.value}"
                )

        return result

    def _check_missing_values(self, data: Dict[str, Any]) -> List[ValidationResult]:
        """Check for inappropriate use of missing value terms"""
        results = []

        # Check type fields
        for field_name in data:
            if field_name in SKIP_PROPERTIES:
                continue

            field_data = data[field_name]
            requirement = self._get_requirement_level(field_name, 'type')

            if requirement:
                missing_results = self._check_field_missing_values(
                    field_name, field_data, requirement
                )
                results.extend(missing_results)

        # Check core fields
        if 'samples_core' in data:
            for field_name, field_data in data['samples_core'].items():
                requirement = self._get_requirement_level(field_name, 'core')

                if requirement:
                    missing_results = self._check_field_missing_values(
                        f"samples_core.{field_name}", field_data, requirement
                    )
                    results.extend(missing_results)

        return results

    def _get_requirement_level(self, field_name: str, field_type: str) -> Optional[str]:
        """Get requirement level for a field"""
        for level in ['mandatory', 'recommended', 'optional']:
            if field_name in self.field_requirements[level][field_type]:
                return level
        return None

    def _check_field_missing_values(self, field_path: str, field_data: Any,
                                    requirement: str) -> List[ValidationResult]:
        """Check a single field for missing values"""
        results = []
        missing_config = MISSING_VALUES.get(requirement, {})

        values_to_check = []

        if isinstance(field_data, dict):
            for key in ['value', 'text', 'term']:
                if key in field_data:
                    values_to_check.append((field_data[key], field_path))
        elif isinstance(field_data, list):
            for i, item in enumerate(field_data):
                if isinstance(item, dict):
                    for key in ['value', 'text', 'term']:
                        if key in item:
                            values_to_check.append((item[key], f"{field_path}[{i}]"))

        for value, path in values_to_check:
            if value in missing_config.get('errors', []):
                results.append(ValidationResult(
                    field_path=path,
                    errors=[f"Field '{path.split('.')[-1]}' contains missing value that "
                            f"is not appropriate for this field"]
                ))
            elif value in missing_config.get('warnings', []):
                results.append(ValidationResult(
                    field_path=path,
                    warnings=[f"Field '{path.split('.')[-1]}' contains missing value that "
                              f"is not appropriate for this field"]
                ))

        return results

    def _validate_ontologies(self, data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate all ontology fields in the data"""
        results = []

        # Collect all ontology terms
        ontology_ids = self._collect_ontology_ids(data)

        # Validate type fields
        for field_name, field_data in data.items():
            if field_name in SKIP_PROPERTIES:
                continue

            if field_name in self.ontology_names:
                onto_results = self._validate_ontology_field(
                    field_name, field_data, self.ontology_names[field_name]
                )
                results.extend(onto_results)

        # Validate core fields
        if 'samples_core' in data:
            # TODO: Add core ontology validation if needed
            pass

        return results

    def _validate_ontology_field(self, field_name: str, field_data: Any,
                                 expected_onto_names: List[str]) -> List[ValidationResult]:
        """Validate a single ontology field"""
        results = []

        if isinstance(field_data, dict) and 'term' in field_data and 'text' in field_data:
            onto_result = self.ontology_validator.validate_ontology_term(
                field_data['term'],
                field_data.get('ontology_name', ''),
                [],  # TODO: Add allowed classes from graph restrictions
                field_data['text']
            )
            if onto_result.errors or onto_result.warnings:
                onto_result.field_path = field_name
                results.append(onto_result)
        elif isinstance(field_data, list):
            for i, item in enumerate(field_data):
                if isinstance(item, dict) and 'term' in item and 'text' in item:
                    onto_result = self.ontology_validator.validate_ontology_term(
                        item['term'],
                        item.get('ontology_name', ''),
                        [],  # TODO: Add allowed classes from graph restrictions
                        item['text']
                    )
                    if onto_result.errors or onto_result.warnings:
                        onto_result.field_path = f"{field_name}[{i}]"
                        results.append(onto_result)

        return results

    def _validate_custom_fields(self, custom_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate custom fields for ontology consistency"""
        results = []

        for field_name, field_data in custom_data.items():
            if isinstance(field_data, dict) and 'term' in field_data and 'text' in field_data:
                onto_result = self.ontology_validator.validate_ontology_term(
                    field_data['term'],
                    field_data.get('ontology_name', ''),
                    [],
                    field_data['text']
                )
                if onto_result.errors or onto_result.warnings:
                    onto_result.field_path = f"custom.{field_name}"
                    results.append(onto_result)

        return results

    def _collect_ontology_ids(self, data: Dict[str, Any]) -> Set[str]:
        """Collect all ontology term IDs from the data"""
        ids = set()

        def extract_ids(obj: Any):
            if isinstance(obj, dict):
                if 'term' in obj and 'text' in obj:
                    ids.add(obj['term'])
                for value in obj.values():
                    extract_ids(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_ids(item)

        extract_ids(data)
        return ids

    def _get_organism_identifier(self, organism: Dict, action: str = 'new') -> str:
        """Get identifier for an organism from the data"""
        col_name = 'biosample_id' if action == 'update' else 'sample_name'

        if 'custom' in organism and col_name in organism['custom']:
            return organism['custom'][col_name]['value']
        elif 'alias' in organism:
            return organism.get('alias', {}).get('value', '')

        return ''

    def _get_record_structure(self, structure: Dict[str, Any], record: Dict[str, Any],
                              record_name: str, action: str) -> Dict[str, Any]:
        """Create structure to return to front-end matching Django format"""
        col_name = 'biosample_id' if action == 'update' else 'sample_name'

        # Initialize the structure
        result = self._parse_data(structure.get('type', {}), record)

        # Add core fields
        if 'samples_core' in record and 'core' in structure:
            result['samples_core'] = self._parse_data(
                structure['core'], record['samples_core']
            )

        # Add custom fields
        if 'custom' in structure:
            result['custom'] = self._parse_data(
                structure['custom'], record.get('custom', {})
            )

            # Ensure the identifier field exists
            if col_name not in result['custom']:
                result['custom'][col_name] = {'value': record_name}

        return result

    def _parse_data(self, structure: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
        """Copy data from record to structure"""
        results = {}

        for k, v in structure.items():
            if isinstance(v, dict):
                if k in record:
                    results[k] = self._convert_to_none(v, record[k])
                else:
                    results[k] = self._convert_to_none(v)
            elif isinstance(v, list):
                results.setdefault(k, [])
                for index, value in enumerate(v):
                    if k in record and index < len(record[k]):
                        results[k].append(self._convert_to_none(value, record[k][index]))
                    else:
                        results[k].append(self._convert_to_none(value))

        return results

    def _convert_to_none(self, structure: Dict[str, Any],
                         data_to_check: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Assign fields to None or copy values"""
        results = {}

        if data_to_check is None:
            for k in structure:
                results[k] = None
        else:
            for k in structure:
                if k in data_to_check:
                    results[k] = data_to_check[k]
                else:
                    results[k] = None

        return results

    def _apply_validation_result_to_structure(self, structure: Dict[str, Any],
                                              result: ValidationResult):
        """Apply validation result to the record structure"""
        # Parse the field path
        path_parts = result.field_path.split('.')

        # Navigate to the correct location in the structure
        current = structure
        for i, part in enumerate(path_parts[:-1]):
            # Handle array indices
            if '[' in part and ']' in part:
                field_name = part[:part.index('[')]
                index = int(part[part.index('[') + 1:part.index(']')])

                if field_name in current and isinstance(current[field_name], list):
                    if index < len(current[field_name]):
                        current = current[field_name][index]
                    else:
                        break
            elif part in current:
                current = current[part]
            else:
                break

        # Apply errors/warnings to the final field
        final_field = path_parts[-1]

        # Handle array indices in final field
        if '[' in final_field and ']' in final_field:
            field_name = final_field[:final_field.index('[')]
            index = int(final_field[final_field.index('[') + 1:final_field.index(']')])

            if field_name in current and isinstance(current[field_name], list):
                if index < len(current[field_name]):
                    target = current[field_name][index]
                    if isinstance(target, dict):
                        if result.errors:
                            target.setdefault('errors', []).extend(result.errors)
                        if result.warnings:
                            target.setdefault('warnings', []).extend(result.warnings)
        elif final_field in current:
            target = current[final_field]
            if isinstance(target, dict):
                if result.errors:
                    target.setdefault('errors', []).extend(result.errors)
                if result.warnings:
                    target.setdefault('warnings', []).extend(result.warnings)
            elif isinstance(target, list):
                # Apply to all items in the list
                for item in target:
                    if isinstance(item, dict):
                        if result.errors:
                            item.setdefault('errors', []).extend(result.errors)
                        if result.warnings:
                            item.setdefault('warnings', []).extend(result.warnings)


def get_submission_status(validation_results: Dict[str, Any]) -> str:
    """Check results for errors and return appropriate submission status"""

    def has_issues(record: Dict[str, Any]) -> bool:
        """Recursively check if record has any errors"""
        for key, value in record.items():
            if key in ['samples_core', 'custom', 'experiments_core']:
                if has_issues(value):
                    return True
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and 'errors' in item and item['errors']:
                        return True
            elif isinstance(value, dict):
                if 'errors' in value and value['errors']:
                    return True
        return False

    # Check all records for errors
    for record_type, records in validation_results.items():
        for record in records:
            if has_issues(record):
                return 'Fix issues'

    return 'Ready for submission'


# Example usage and integration
if __name__ == "__main__":
    # Example organism data
    sample_organisms = [
        {
            "samples_core": {
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026",
                    "ontology_name": "OBI"
                },
                "project": {"value": "FAANG"},
                "sample_description": {"value": "Adult female Holstein cattle"}
            },
            "organism": {
                "text": "Bos taurus",
                "term": "NCBITaxon:9913",
                "ontology_name": "NCBITaxon"
            },
            "sex": {
                "text": "female",
                "term": "PATO:0000383",
                "ontology_name": "PATO"
            },
            "birth_date": {
                "value": "2020-05-15",
                "units": "YYYY-MM-DD"
            },
            "breed": {
                "text": "Holstein",
                "term": "LBO:0000156",
                "ontology_name": "LBO"
            },
            "custom": {
                "sample_name": {"value": "CATTLE_001"}
            }
        },
        {
            "samples_core": {
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026",
                    "ontology_name": "OBI"
                },
                "project": {"value": "FAANG"},
                "sample_description": {"value": "Calf from CATTLE_001"}
            },
            "organism": {
                "text": "Bos taurus",
                "term": "NCBITaxon:9913",
                "ontology_name": "NCBITaxon"
            },
            "sex": {
                "text": "male",
                "term": "PATO:0000384",
                "ontology_name": "PATO"
            },
            "child_of": [
                {"value": "CATTLE_001"}
            ],
            "custom": {
                "sample_name": {"value": "CATTLE_002"}
            }
        }
    ]

    # Example structure from Django
    structure = {
        "organism": {
            "type": {
                "organism": {"text": None, "term": None, "ontology_name": None},
                "sex": {"text": None, "term": None, "ontology_name": None},
                "birth_date": {"value": None, "units": None},
                "breed": {"text": None, "term": None, "ontology_name": None},
                "health_status": [{"text": None, "term": None, "ontology_name": None}],
                "child_of": [{"value": None}]
            },
            "core": {
                "material": {"text": None, "term": None, "ontology_name": None},
                "project": {"value": None},
                "sample_description": {"value": None}
            },
            "custom": {
                "sample_name": {"value": None}
            }
        }
    }

    # Validate batch
    validator = EnhancedFAANGOrganismValidator()
    results = validator.validate_organism_batch(
        sample_organisms,
        structure,
        action='new',
        check_relationships=True
    )

    # Get submission status
    status = get_submission_status(results)

    print(f"Validation complete!")
    print(f"Submission status: {status}")
    print(f"\nValidation results:")
    print(json.dumps(results, indent=2))

    # Example of how to integrate with FastAPI
    """
    from fastapi import FastAPI, HTTPException
    from typing import List, Dict, Any

    app = FastAPI()

    @app.post("/validate/samples/organism")
    async def validate_organisms(
        organisms: List[Dict[str, Any]],
        structure: Dict[str, Any],
        action: str = "new"
    ):
        validator = EnhancedFAANGOrganismValidator()

        try:
            validation_results = validator.validate_organism_batch(
                organisms, 
                structure,
                action=action,
                check_relationships=True
            )

            submission_status = get_submission_status(validation_results)

            return {
                "validation_results": validation_results,
                "submission_status": submission_status
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    """