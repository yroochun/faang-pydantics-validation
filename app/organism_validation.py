# complete_organism_validation.py
"""
Complete organism validation implementation matching Django functionality
"""

from pydantic import BaseModel, Field, validator, ValidationError
from typing import List, Optional, Union, Dict, Any, Tuple, Set
import re
from datetime import datetime
import requests
import asyncio
import aiohttp
from collections import defaultdict
import json

from organism_ruleset import (
    FAANGOrganismSample, Organism, Sex, BirthDate, Breed, HealthStatus,
    DateUnits, WeightUnits, TimeUnits, DeliveryTiming, DeliveryEase,
    BaseOntologyTerm, SampleCoreMetadata
)

from constants import (
    SPECIES_BREED_LINKS, MISSING_VALUES, ALLOWED_RELATIONSHIPS,
    SKIP_PROPERTIES, ORGANISM_URL, SAMPLE_CORE_URL,
    ELIXIR_VALIDATOR_URL, ALLOWED_SAMPLES_TYPES
)


class CompleteOrganismValidator:
    """Complete validator matching Django functionality"""

    def __init__(self):
        self.ontology_cache = {}
        self.schema_cache = {}
        self.biosamples_cache = {}

        # Load schemas
        self._load_schemas()

        # Extract field requirements from schemas
        self.field_requirements = self._extract_field_requirements()
        self.ontology_names = self._extract_ontology_names()

    def _load_schemas(self):
        """Load required JSON schemas"""
        try:
            response = requests.get(ORGANISM_URL, timeout=30)
            response.raise_for_status()
            self.organism_schema = response.json()
        except Exception as e:
            print(f"Error loading organism schema: {e}")
            self.organism_schema = {}

        try:
            response = requests.get(SAMPLE_CORE_URL, timeout=30)
            response.raise_for_status()
            self.samples_core_schema = response.json()
        except Exception as e:
            print(f"Error loading samples core schema: {e}")
            self.samples_core_schema = {}

    def validate_batch(self, json_data: Dict[str, List[Dict]],
                       structure: Dict[str, Any],
                       action: str = 'new') -> Dict[str, Any]:
        """
        Main entry point matching Django's validation flow

        Args:
            json_data: {"organism": [...]} format from Django
            structure: Structure definition from Django
            action: 'new' or 'update'

        Returns:
            Validation document in Django format
        """
        organisms = json_data.get('organism', [])

        # 1. For updates, validate BioSample IDs first
        if action == 'update':
            biosample_errors = self._verify_biosample_ids(organisms)
            if biosample_errors:
                return {
                    'organism': [{
                        'errors': biosample_errors,
                        'submission_status': 'Fix issues'
                    }]
                }

        # 2. Collect all ontology IDs for batch fetching (like Django)
        all_ontology_ids = self._collect_all_ontology_ids(organisms)
        self._batch_fetch_ontology_data(all_ontology_ids)

        # 3. Build validation document structure
        validation_document = {'organism': []}

        # 4. First pass: validate individual organisms
        for i, org_data in enumerate(organisms):
            record_name = self._get_record_name(org_data, i, 'organism', action)

            # Create Django-style record structure
            record_structure = self._get_record_structure(
                structure.get('organism', {}),
                org_data,
                record_name
            )

            # Run all validations
            self._validate_single_organism(
                org_data,
                record_structure,
                action
            )

            validation_document['organism'].append(record_structure)

        # 5. Second pass: validate relationships
        if len(organisms) > 1:
            self._validate_relationships_batch(
                organisms,
                validation_document['organism'],
                action
            )

        return validation_document

    def _verify_biosample_ids(self, organisms: List[Dict]) -> List[str]:
        """Verify BioSample IDs for update action"""
        errors = []
        biosample_pattern = re.compile(r"^SAM[AED][AG]?\d+$")

        for org in organisms:
            biosample_id = org.get('custom', {}).get('biosample_id', {}).get('value', '')
            if not biosample_pattern.match(biosample_id):
                errors.append(f"Invalid BioSample ID format: {biosample_id}")

        return errors

    def _collect_all_ontology_ids(self, organisms: List[Dict]) -> Set[str]:
        """Collect all ontology IDs from all organisms for batch fetching"""
        ids = set()

        def extract_ids(obj: Any):
            if isinstance(obj, dict):
                if 'term' in obj and obj['term'] not in ['restricted access', 'not applicable', 'not collected',
                                                         'not provided']:
                    ids.add(obj['term'])
                for value in obj.values():
                    extract_ids(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_ids(item)

        for org in organisms:
            extract_ids(org)

        return ids

    def _batch_fetch_ontology_data(self, ontology_ids: Set[str]):
        """Batch fetch ontology data from OLS"""
        # Use async fetching like Django
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._fetch_all_terms(ontology_ids))

    async def _fetch_all_terms(self, ids: Set[str]):
        """Async fetch all ontology terms"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for term_id in ids:
                if term_id not in self.ontology_cache:
                    task = asyncio.create_task(self._fetch_term(session, term_id))
                    tasks.append(task)

            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_term(self, session: aiohttp.ClientSession, term_id: str):
        """Fetch single term from OLS"""
        try:
            url = f"http://www.ebi.ac.uk/ols/api/search?q={term_id.replace(':', '_')}&rows=100"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.ontology_cache[term_id] = data.get('response', {}).get('docs', [])
        except Exception as e:
            print(f"Error fetching {term_id}: {e}")

    def _validate_single_organism(self, org_data: Dict, record_structure: Dict, action: str):
        """Validate a single organism and apply results to structure"""

        # 1. Schema validation using Elixir validator
        if self.organism_schema:
            elixir_errors = self._validate_with_elixir(org_data, self.organism_schema)
            self._apply_elixir_errors(record_structure, elixir_errors)

        # 2. Pydantic validation
        try:
            model = FAANGOrganismSample(**org_data)

            # 3. Additional validations

            # Check recommended fields
            self._check_recommended_fields(org_data, record_structure)

            # Validate all date fields (not just birth_date)
            self._validate_all_dates(org_data, record_structure)

            # Check missing values
            self._check_missing_values(org_data, record_structure)

            # Validate ontology text consistency
            self._validate_ontology_consistency(org_data, record_structure)

            # Breed-species validation
            if 'breed' in org_data and 'organism' in org_data:
                self._validate_breed_species(org_data, record_structure)

            # Validate custom fields
            if 'custom' in org_data:
                self._validate_custom_fields(org_data['custom'], record_structure['custom'])

        except ValidationError as e:
            self._apply_pydantic_errors(record_structure, e)

    def _validate_with_elixir(self, data: Dict, schema: Dict) -> List[Dict]:
        """Call Elixir validator"""
        try:
            json_to_send = {
                'schema': schema,
                'object': data
            }
            response = requests.post(ELIXIR_VALIDATOR_URL, json=json_to_send, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Elixir validator error: {e}")
            return []

    def _check_recommended_fields(self, org_data: Dict, record_structure: Dict):
        """Check for missing recommended fields"""
        # Check type-level recommended fields
        for field in self.field_requirements['recommended']['type']:
            if field not in org_data or org_data[field] is None:
                if field in record_structure:
                    self._add_warning(record_structure[field],
                                      'This item is recommended but was not provided')

        # Check core-level recommended fields
        if 'samples_core' in org_data:
            for field in self.field_requirements['recommended']['core']:
                if field not in org_data['samples_core'] or org_data['samples_core'][field] is None:
                    if field in record_structure['samples_core']:
                        self._add_warning(record_structure['samples_core'][field],
                                          'This item is recommended but was not provided')

    def _validate_all_dates(self, org_data: Dict, record_structure: Dict):
        """Validate all date fields, not just birth_date"""

        def check_dates_in_dict(data_dict: Dict, structure_dict: Dict):
            for field_name, field_value in data_dict.items():
                if 'date' in field_name and isinstance(field_value, dict):
                    if 'value' in field_value and 'units' in field_value:
                        if not self._is_date_format_valid(field_value['value'], field_value['units']):
                            self._add_error(structure_dict.get(field_name, {}),
                                            f"Date units: {field_value['units']} should be "
                                            f"consistent with date value: {field_value['value']}")

        # Check top level
        check_dates_in_dict(org_data, record_structure)

        # Check samples_core
        if 'samples_core' in org_data:
            check_dates_in_dict(org_data['samples_core'], record_structure.get('samples_core', {}))

    def _is_date_format_valid(self, date_value: str, date_units: str) -> bool:
        """Check if date format matches units"""
        if date_value in ["not applicable", "not collected", "not provided", "restricted access"]:
            return True

        format_map = {
            'YYYY-MM-DD': '%Y-%m-%d',
            'YYYY-MM': '%Y-%m',
            'YYYY': '%Y'
        }

        date_format = format_map.get(date_units)
        if not date_format:
            return True

        try:
            datetime.strptime(date_value, date_format)
            return True
        except ValueError:
            return False

    def _check_missing_values(self, org_data: Dict, record_structure: Dict):
        """Check for inappropriate missing values"""

        def check_field_missing_values(field_name: str, field_data: Any,
                                       structure_data: Dict, requirement: str):
            missing_config = MISSING_VALUES.get(requirement, {})

            value = None
            if isinstance(field_data, dict):
                value = field_data.get('value') or field_data.get('text')

            if value:
                if value in missing_config.get('errors', []):
                    self._add_error(structure_data,
                                    f"Field '{field_name}' contains missing value that is "
                                    f"not appropriate for this field")
                elif value in missing_config.get('warnings', []):
                    self._add_warning(structure_data,
                                      f"Field '{field_name}' contains missing value that may "
                                      f"not be appropriate for this field")

        # Check type fields
        for field_name in org_data:
            if field_name in SKIP_PROPERTIES:
                continue

            requirement = self._get_field_requirement(field_name, 'type')
            if requirement and field_name in record_structure:
                if isinstance(org_data[field_name], list):
                    for i, item in enumerate(org_data[field_name]):
                        if i < len(record_structure[field_name]):
                            check_field_missing_values(
                                field_name, item,
                                record_structure[field_name][i], requirement
                            )
                else:
                    check_field_missing_values(
                        field_name, org_data[field_name],
                        record_structure[field_name], requirement
                    )

        # Check core fields
        if 'samples_core' in org_data:
            for field_name in org_data['samples_core']:
                requirement = self._get_field_requirement(field_name, 'core')
                if requirement and field_name in record_structure['samples_core']:
                    check_field_missing_values(
                        field_name, org_data['samples_core'][field_name],
                        record_structure['samples_core'][field_name], requirement
                    )

    def _validate_ontology_consistency(self, org_data: Dict, record_structure: Dict):
        """Validate ontology text matches OLS labels"""

        def check_ontology_field(field_data: Any, structure_data: Dict,
                                 expected_ontology: str = None):
            if isinstance(field_data, dict) and 'term' in field_data and 'text' in field_data:
                term = field_data['term']
                text = field_data['text']

                if term in self.ontology_cache:
                    ols_docs = self.ontology_cache[term]

                    # Find matching labels
                    labels = []
                    for doc in ols_docs:
                        if expected_ontology:
                            if doc.get('ontology_name', '').lower() == expected_ontology.lower():
                                labels.append(doc.get('label', '').lower())
                        else:
                            labels.append(doc.get('label', '').lower())

                    if labels and text.lower() not in labels:
                        self._add_warning(structure_data,
                                          f"Provided value '{text}' doesn't precisely match "
                                          f"'{labels[0]}' for term '{term}'")

        # Check all ontology fields
        for field_name, field_data in org_data.items():
            if field_name in SKIP_PROPERTIES:
                continue

            expected_ontology = None
            if field_name in self.ontology_names:
                expected_ontology = self.ontology_names[field_name][0] if self.ontology_names[field_name] else None

            if field_name in record_structure:
                if isinstance(field_data, list):
                    for i, item in enumerate(field_data):
                        if i < len(record_structure[field_name]):
                            check_ontology_field(item, record_structure[field_name][i], expected_ontology)
                else:
                    check_ontology_field(field_data, record_structure[field_name], expected_ontology)

        # Check core fields
        if 'samples_core' in org_data and 'samples_core' in record_structure:
            for field_name, field_data in org_data['samples_core'].items():
                if field_name in record_structure['samples_core']:
                    check_ontology_field(field_data, record_structure['samples_core'][field_name])

    def _validate_breed_species(self, org_data: Dict, record_structure: Dict):
        """Validate breed is appropriate for species using Elixir validator"""
        organism_term = org_data.get('organism', {}).get('term')
        breed_term = org_data.get('breed', {}).get('term')

        if organism_term in SPECIES_BREED_LINKS and breed_term and breed_term not in ['not applicable',
                                                                                      'restricted access']:
            # Create schema for breed validation
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

            # Validate with Elixir
            errors = self._validate_with_elixir(breed_term, breed_schema)
            if errors:
                self._add_error(record_structure.get('organism', {}),
                                f"Breed '{org_data['breed']['text']}' doesn't match the animal "
                                f"specie: '{org_data['organism']['text']}'")

    def _validate_custom_fields(self, custom_data: Dict, custom_structure: Dict):
        """Validate custom fields for ontology consistency"""
        for field_name, field_value in custom_data.items():
            if isinstance(field_value, dict) and 'term' in field_value and 'text' in field_value:
                term = field_value['term']
                text = field_value['text']

                if term in self.ontology_cache and field_name in custom_structure:
                    ols_docs = self.ontology_cache[term]
                    if ols_docs:
                        label = ols_docs[0].get('label', '').lower()
                        if text.lower() != label:
                            self._add_warning(custom_structure[field_name],
                                              f"Provided value '{text}' doesn't precisely match "
                                              f"'{label}' for term '{term}'")

    def _validate_relationships_batch(self, organisms: List[Dict],
                                      validation_records: List[Dict],
                                      action: str):
        """Validate relationships across all organisms"""
        # Build organism map
        organism_map = {}
        for i, org in enumerate(organisms):
            name = self._get_record_name(org, i, 'organism', action)
            organism_map[name] = (org, validation_records[i])

        # Collect BioSample IDs that need fetching
        biosample_ids_to_fetch = set()
        for org, _ in organism_map.values():
            child_of = org.get('child_of', [])
            if isinstance(child_of, dict):
                child_of = [child_of]

            for parent_ref in child_of:
                parent_id = parent_ref.get('value', '')
                if parent_id.startswith('SAM') and parent_id not in organism_map:
                    biosample_ids_to_fetch.add(parent_id)

        # Fetch BioSample data if needed
        if biosample_ids_to_fetch:
            self._fetch_biosample_data_sync(list(biosample_ids_to_fetch))

        # Check each organism's relationships
        for name, (org, record) in organism_map.items():
            child_of = org.get('child_of', [])
            if not child_of:
                continue

            if isinstance(child_of, dict):
                child_of = [child_of]

            for i, parent_ref in enumerate(child_of):
                parent_id = parent_ref.get('value', '')

                if parent_id == 'restricted access':
                    continue

                # Initialize child_of in record if needed
                if 'child_of' not in record:
                    record['child_of'] = []
                    for _ in child_of:
                        record['child_of'].append({'value': None})

                # Check if parent exists
                if parent_id not in organism_map and parent_id not in self.biosamples_cache:
                    self._add_error(record['child_of'][i],
                                    f"Relationships part: no entity '{parent_id}' found")
                    continue

                # Get parent data
                if parent_id in organism_map:
                    parent_org = organism_map[parent_id][0]
                    parent_species = parent_org.get('organism', {}).get('text', '')
                    parent_material = 'organism'
                else:
                    parent_data = self.biosamples_cache.get(parent_id, {})
                    parent_species = parent_data.get('organism', '')
                    parent_material = parent_data.get('material', '').lower().replace(' ', '_')

                # Check species match
                current_species = org.get('organism', {}).get('text', '')
                if current_species and parent_species and current_species != parent_species:
                    self._add_error(record['child_of'][i],
                                    f"Relationships part: the specie of the child "
                                    f"'{current_species}' doesn't match the specie "
                                    f"of the parent '{parent_species}'")

                # Check material type is allowed
                allowed_materials = ALLOWED_RELATIONSHIPS.get('organism', [])
                if parent_material and parent_material not in allowed_materials:
                    self._add_error(record['child_of'][i],
                                    f"Relationships part: referenced entity '{parent_id}' "
                                    f"does not match condition 'should be {' or '.join(allowed_materials)}'")

                # Check for circular relationships
                if parent_id in organism_map:
                    parent_child_of = organism_map[parent_id][0].get('child_of', [])
                    if isinstance(parent_child_of, dict):
                        parent_child_of = [parent_child_of]

                    for grandparent in parent_child_of:
                        if grandparent.get('value') == name:
                            self._add_error(record['child_of'][i],
                                            f"Relationships part: parent '{parent_id}' is "
                                            f"listing the child as its parent")

    def _fetch_biosample_data_sync(self, biosample_ids: List[str]):
        """Synchronously fetch BioSample data"""
        for sample_id in biosample_ids:
            if sample_id in self.biosamples_cache:
                continue

            try:
                url = f"https://www.ebi.ac.uk/biosamples/samples/{sample_id}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()

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

    # Helper methods

    def _get_record_name(self, record: Dict, index: int, name: str, action: str) -> str:
        """Get record identifier"""
        col_name = 'biosample_id' if action == 'update' else 'sample_name'

        if 'custom' in record and col_name in record['custom']:
            return record['custom'][col_name]['value']
        elif 'alias' in record:
            return record.get('alias', {}).get('value', f"{name}_{index + 1}")

        return f"{name}_{index + 1}"

    def _get_record_structure(self, structure: Dict, record: Dict, record_name: str) -> Dict:
        """Create Django-style record structure"""
        result = self._parse_data(structure.get('type', {}), record)

        if 'samples_core' in record and 'core' in structure:
            result['samples_core'] = self._parse_data(structure['core'], record['samples_core'])

        if 'custom' in structure:
            result['custom'] = self._parse_data(structure['custom'], record.get('custom', {}))

        return result

    def _parse_data(self, structure: Dict, record: Dict) -> Dict:
        """Parse data according to structure"""
        results = {}

        for k, v in structure.items():
            if isinstance(v, dict):
                if k in record:
                    results[k] = self._convert_to_structure(v, record[k])
                else:
                    results[k] = self._convert_to_structure(v, None)
            elif isinstance(v, list):
                results[k] = []
                if k in record and isinstance(record[k], list):
                    for i, item in enumerate(record[k]):
                        if i < len(v):
                            results[k].append(self._convert_to_structure(v[i], item))
                        else:
                            # If record has more items than structure, use first structure as template
                            results[k].append(self._convert_to_structure(v[0], item))
                else:
                    # If no data, create empty structure
                    for template in v:
                        results[k].append(self._convert_to_structure(template, None))

        return results

    def _convert_to_structure(self, template: Dict, data: Any) -> Dict:
        """Convert data to match template structure"""
        result = {}

        if data is None:
            for k in template:
                result[k] = None
        else:
            for k in template:
                if k in data:
                    result[k] = data[k]
                else:
                    result[k] = None

        return result

    def _add_error(self, field_dict: Dict, error: str):
        """Add error to field"""
        if isinstance(field_dict, dict):
            field_dict.setdefault('errors', [])
            if error not in field_dict['errors']:  # Avoid duplicates
                field_dict['errors'].append(error)

    def _add_warning(self, field_dict: Dict, warning: str):
        """Add warning to field"""
        if isinstance(field_dict, dict):
            field_dict.setdefault('warnings', [])
            if warning not in field_dict['warnings']:  # Avoid duplicates
                field_dict['warnings'].append(warning)

    def _apply_elixir_errors(self, structure: Dict, errors: List[Dict]):
        """Apply Elixir validator errors to structure"""
        for error_item in errors:
            path = error_item.get('dataPath', '')
            errors = [e for e in error_item.get('errors', [])
                      if e != 'should match exactly one schema in oneOf']

            if errors:
                # Parse path and apply to structure
                self._apply_errors_to_path(structure, path, errors)

    def _apply_pydantic_errors(self, structure: Dict, validation_error: ValidationError):
        """Apply Pydantic errors to structure"""
        for error in validation_error.errors():
            path = '.'.join(str(x) for x in error['loc'])
            error_msg = error['msg']
            self._apply_errors_to_path(structure, path, [error_msg])

    def _apply_errors_to_path(self, structure: Dict, path: str, errors: List[str]):
        """Apply errors to specific path in structure"""
        if not path:
            return

        # Handle different path formats
        # Elixir uses paths like: /organism/term or /child_of[0]/value
        # Pydantic uses paths like: organism.term or child_of.0.value

        # Normalize path
        if path.startswith('/'):
            path = path[1:]
        path = path.replace('/', '.')

        # Parse array indices
        parts = []
        for part in path.split('.'):
            if '[' in part and ']' in part:
                field_name = part[:part.index('[')]
                index = int(part[part.index('[') + 1:part.index(']')])
                parts.extend([field_name, str(index)])
            else:
                parts.append(part)

        # Navigate to the target field
        current = structure
        for i, part in enumerate(parts):
            if part.isdigit():
                # Array index
                index = int(part)
                if isinstance(current, list) and index < len(current):
                    current = current[index]
                else:
                    return
            else:
                # Object field
                if isinstance(current, dict) and part in current:
                    # If this is the last part, add the error here
                    if i == len(parts) - 1:
                        if isinstance(current[part], dict):
                            current[part].setdefault('errors', []).extend(errors)
                        elif isinstance(current[part], list):
                            # Add error to all items in the list
                            for item in current[part]:
                                if isinstance(item, dict):
                                    item.setdefault('errors', []).extend(errors)
                    else:
                        current = current[part]
                else:
                    return

    def _extract_field_requirements(self) -> Dict[str, Dict[str, List[str]]]:
        """Extract field requirements from schemas"""
        requirements = {
            'mandatory': {'core': [], 'type': []},
            'recommended': {'core': [], 'type': []},
            'optional': {'core': [], 'type': []}
        }

        # Extract from organism schema
        if self.organism_schema and 'properties' in self.organism_schema:
            for field_name, field_def in self.organism_schema['properties'].items():
                if field_name not in SKIP_PROPERTIES:
                    requirement = self._get_field_requirement_from_schema(field_def)
                    if requirement:
                        requirements[requirement]['type'].append(field_name)

        # Extract from core schema
        if self.samples_core_schema and 'properties' in self.samples_core_schema:
            for field_name, field_def in self.samples_core_schema['properties'].items():
                if field_name not in SKIP_PROPERTIES:
                    requirement = self._get_field_requirement_from_schema(field_def)
                    if requirement:
                        requirements[requirement]['core'].append(field_name)

        return requirements

    def _get_field_requirement_from_schema(self, field_def: Dict) -> Optional[str]:
        """Get requirement level from field definition"""
        if field_def.get('type') == 'object':
            mandatory_prop = field_def.get('properties', {}).get('mandatory', {})
            if 'const' in mandatory_prop:
                return mandatory_prop['const']
        elif field_def.get('type') == 'array':
            items_mandatory = field_def.get('items', {}).get('properties', {}).get('mandatory', {})
            if 'const' in items_mandatory:
                return items_mandatory['const']
        return None

    def _get_field_requirement(self, field_name: str, field_type: str) -> Optional[str]:
        """Get requirement level for a specific field"""
        for level in ['mandatory', 'recommended', 'optional']:
            if field_name in self.field_requirements[level][field_type]:
                return level
        return None

    def _extract_ontology_names(self) -> Dict[str, List[str]]:
        """Extract expected ontology names from schema"""
        ontology_names = {}

        if self.organism_schema and 'properties' in self.organism_schema:
            for field_name, field_def in self.organism_schema['properties'].items():
                if field_name not in SKIP_PROPERTIES:
                    names = self._get_ontology_names_from_field(field_def)
                    if names:
                        ontology_names[field_name] = names

        return ontology_names

    def _get_ontology_names_from_field(self, field_def: Dict) -> List[str]:
        """Extract ontology names from field definition"""
        names = []

        if field_def.get('type') == 'object':
            props = field_def.get('properties', {})
            if 'ontology_name' in props:
                if 'const' in props['ontology_name']:
                    names.append(props['ontology_name']['const'].lower())
                elif 'enum' in props['ontology_name']:
                    names.extend([n.lower() for n in props['ontology_name']['enum']])
        elif field_def.get('type') == 'array':
            items_props = field_def.get('items', {}).get('properties', {})
            if 'ontology_name' in items_props:
                if 'const' in items_props['ontology_name']:
                    names.append(items_props['ontology_name']['const'].lower())
                elif 'enum' in items_props['ontology_name']:
                    names.extend([n.lower() for n in items_props['ontology_name']['enum']])

        return names


def get_submission_status(validation_results: Dict[str, Any]) -> str:
    """Check results for errors and return appropriate submission status"""

    def has_issues(record: Dict[str, Any]) -> bool:
        """Recursively check if record has any errors"""
        for key, value in record.items():
            if key in ['samples_core', 'custom', 'experiments_core',
                       'dna-binding_proteins', 'input_dna', 'teleostei_embryo',
                       'teleostei_post-hatching']:
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


# Integration with existing code
def validate_organisms_for_django(json_data: Dict[str, List[Dict]],
                                  structure: Dict[str, Any],
                                  action: str = 'new') -> Dict[str, Any]:
    """
    Main entry point for Django compatibility

    Args:
        json_data: {"organism": [...]} format
        structure: Django structure definition
        action: 'new' or 'update'

    Returns:
        Validation results in Django format with submission status
    """
    validator = CompleteOrganismValidator()
    validation_results = validator.validate_batch(json_data, structure, action)

    # Add submission status
    submission_status = get_submission_status(validation_results)

    return {
        'validation_results': validation_results,
        'submission_status': submission_status
    }


# Async version for better performance
class AsyncOrganismValidator(CompleteOrganismValidator):
    """Async version of the validator for better performance"""

    async def validate_batch_async(self, json_data: Dict[str, List[Dict]],
                                   structure: Dict[str, Any],
                                   action: str = 'new') -> Dict[str, Any]:
        """Async version of validate_batch"""
        organisms = json_data.get('organism', [])

        # 1. For updates, validate BioSample IDs first
        if action == 'update':
            biosample_errors = self._verify_biosample_ids(organisms)
            if biosample_errors:
                return {
                    'organism': [{
                        'errors': biosample_errors,
                        'submission_status': 'Fix issues'
                    }]
                }

        # 2. Collect and fetch ontology data asynchronously
        all_ontology_ids = self._collect_all_ontology_ids(organisms)
        await self._fetch_all_terms(all_ontology_ids)

        # 3. Fetch BioSamples data if needed
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
            await self._fetch_all_biosamples(list(biosample_ids))

        # 4. Continue with synchronous validation
        validation_document = {'organism': []}

        for i, org_data in enumerate(organisms):
            record_name = self._get_record_name(org_data, i, 'organism', action)
            record_structure = self._get_record_structure(
                structure.get('organism', {}),
                org_data,
                record_name
            )

            self._validate_single_organism(org_data, record_structure, action)
            validation_document['organism'].append(record_structure)

        # 5. Validate relationships
        if len(organisms) > 1:
            self._validate_relationships_batch(
                organisms,
                validation_document['organism'],
                action
            )

        return validation_document

    async def _fetch_all_biosamples(self, biosample_ids: List[str]):
        """Async fetch BioSamples data"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for sample_id in biosample_ids:
                if sample_id not in self.biosamples_cache:
                    task = asyncio.create_task(
                        self._fetch_biosample(session, sample_id)
                    )
                    tasks.append(task)

            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_biosample(self, session: aiohttp.ClientSession, sample_id: str):
        """Fetch single BioSample"""
        try:
            url = f"https://www.ebi.ac.uk/biosamples/samples/{sample_id}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

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


# FastAPI integration example
"""
from fastapi import FastAPI, HTTPException
from typing import Dict, Any
import asyncio

app = FastAPI()

@app.post("/validate/samples")
async def validate_samples(
    json_data: Dict[str, List[Dict]],
    structure: Dict[str, Any],
    action: str = "new",
    validation_type: str = "organism"
):
    '''
    Validate samples matching Django interface

    Args:
        json_data: Sample data in Django format
        structure: Structure definition
        action: 'new' or 'update'
        validation_type: Type of validation (organism, specimen, etc.)
    '''

    if validation_type != "organism":
        raise HTTPException(
            status_code=400, 
            detail=f"Validation type '{validation_type}' not yet implemented"
        )

    # Use async validator for better performance
    validator = AsyncOrganismValidator()

    try:
        validation_results = await validator.validate_batch_async(
            json_data, 
            structure, 
            action
        )

        submission_status = get_submission_status(validation_results)

        return {
            "validation_results": validation_results,
            "submission_status": submission_status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/validate/samples/sync")
def validate_samples_sync(
    json_data: Dict[str, List[Dict]],
    structure: Dict[str, Any],
    action: str = "new"
):
    '''Synchronous version of validation endpoint'''
    return validate_organisms_for_django(json_data, structure, action)
"""


# Celery task replacement
def validate_organism_task(json_data: Dict[str, List[Dict]],
                           structure: Dict[str, Any],
                           action: str = 'new') -> Dict[str, Any]:
    """
    Replacement for Django Celery task
    Can be used with any task queue system (Celery, RQ, etc.)
    """
    try:
        validator = CompleteOrganismValidator()
        validation_results = validator.validate_batch(json_data, structure, action)
        submission_status = get_submission_status(validation_results)

        return {
            'status': 'success',
            'validation_results': validation_results,
            'submission_status': submission_status
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc()
        }


# Utility functions for migration
def migrate_django_to_pydantic(django_data: Dict) -> Dict:
    """Convert Django validation format to Pydantic format if needed"""
    # Django and Pydantic should use the same format
    # This is here in case any conversion is needed
    return django_data


def compare_validation_results(django_results: Dict, pydantic_results: Dict) -> Dict:
    """Compare Django and Pydantic validation results for testing"""
    differences = {
        'missing_in_pydantic': [],
        'missing_in_django': [],
        'different_errors': []
    }

    # Deep comparison of results
    def compare_records(django_rec: Dict, pydantic_rec: Dict, path: str = ''):
        for key in set(django_rec.keys()) | set(pydantic_rec.keys()):
            current_path = f"{path}.{key}" if path else key

            if key not in pydantic_rec:
                differences['missing_in_pydantic'].append(current_path)
            elif key not in django_rec:
                differences['missing_in_django'].append(current_path)
            else:
                # Compare values
                django_val = django_rec[key]
                pydantic_val = pydantic_rec[key]

                if isinstance(django_val, dict) and isinstance(pydantic_val, dict):
                    compare_records(django_val, pydantic_val, current_path)
                elif isinstance(django_val, list) and isinstance(pydantic_val, list):
                    for i, (d_item, p_item) in enumerate(zip(django_val, pydantic_val)):
                        if isinstance(d_item, dict) and isinstance(p_item, dict):
                            compare_records(d_item, p_item, f"{current_path}[{i}]")

    # Compare each organism
    for record_type in django_results:
        if record_type in pydantic_results:
            django_records = django_results[record_type]
            pydantic_records = pydantic_results[record_type]

            for i, (d_rec, p_rec) in enumerate(zip(django_records, pydantic_records)):
                compare_records(d_rec, p_rec, f"{record_type}[{i}]")

    return differences


# Example usage matching Django interface
if __name__ == "__main__":
    import traceback

    json_string = """
        {
            "organism": [
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Adult female, 23.5 months of age, Thoroughbred"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "female",
                        "term": "PATO:0000383"
                    },
                    "birth_date": {
                        "value": "2009-04",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H1"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Foal, 9 days old, Thoroughbred"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "female",
                        "term": "PATO:0000383"
                    },
                    "birth_date": {
                        "value": "2014-07",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H2"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Whole embryo, 34 days gestational age, Thoroughbred"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "female",
                        "term": "PATO:0000383"
                    },
                    "birth_date": {
                        "value": "2016-01",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H3"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Endometrium (pregnant day 16)"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "female",
                        "term": "PATO:0000383"
                    },
                    "birth_date": {
                        "value": "2016-01",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H4"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Endometrium (pregnant day 50)"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "female",
                        "term": "PATO:0000383"
                    },
                    "birth_date": {
                        "value": "2016-01",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H5"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Adult male, 4 years of age, Thoroughbred"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "male",
                        "term": "PATO:0000384"
                    },
                    "birth_date": {
                        "value": "2016-01",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H6"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Adult"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "male",
                        "term": "PATO:0000384"
                    },
                    "birth_date": {
                        "value": "2014-07",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H7"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Adult, Thoroughbred"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "male",
                        "term": "PATO:0000384"
                    },
                    "birth_date": {
                        "value": "2014-07",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H8"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Full term, Thoroughbred"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "female",
                        "term": "PATO:0000383"
                    },
                    "birth_date": {
                        "value": "2014-07",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H9"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Adult"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "male",
                        "term": "PATO:0000384"
                    },
                    "birth_date": {
                        "value": "2014-07",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H10"
                        }
                    }
                },
                {
                    "samples_core": {
                        "sample_description": {
                            "value": "Foal"
                        },
                        "material": {
                            "text": "organism",
                            "term": "OBI:0100026"
                        },
                        "project": {
                            "value": "FAANG"
                        }
                    },
                    "organism": {
                        "text": "Equus caballus",
                        "term": "NCBITaxon:9796"
                    },
                    "sex": {
                        "text": "male",
                        "term": "PATO:0000384"
                    },
                    "birth_date": {
                        "value": "2013-02",
                        "units": "YYYY-MM"
                    },
                    "breed": {
                        "text": "Thoroughbred",
                        "term": "LBO:0000910"
                    },
                    "health_status": [
                        {
                            "text": "normal",
                            "term": "PATO:0000461"
                        }
                    ],
                    "custom": {
                        "sample_name": {
                            "value": "ECA_UKY_H11"
                        }
                    }
                }
            ]
        }
        """

    # Convert the JSON string into a Python dictionary
    data = json.loads(json_string)
    sample_organisms = data["organism"]

    # Example Django-style input
    json_data = {
        "organism": [
            {
                "samples_core": {
                    "sample_description": {"value": "Adult female Holstein cattle"},
                    "material": {"text": "organism", "term": "OBI:0100026", "ontology_name": "OBI"},
                    "project": {"value": "FAANG"}
                },
                "organism": {"text": "Bos taurus", "term": "NCBITaxon:9913", "ontology_name": "NCBITaxon"},
                "sex": {"text": "female", "term": "PATO:0000383", "ontology_name": "PATO"},
                "birth_date": {"value": "2020-05-15", "units": "YYYY-MM-DD"},
                "breed": {"text": "Holstein", "term": "LBO:0000156", "ontology_name": "LBO"},
                "custom": {"sample_name": {"value": "CATTLE_001"}}
            },
            {
                "samples_core": {
                    "sample_description": {"value": "Calf from CATTLE_001"},
                    "material": {"text": "organism", "term": "OBI:0100026", "ontology_name": "OBI"},
                    "project": {"value": "FAANG"}
                },
                "organism": {"text": "Bos taurus", "term": "NCBITaxon:9913", "ontology_name": "NCBITaxon"},
                "sex": {"text": "male", "term": "PATO:0000384", "ontology_name": "PATO"},
                "child_of": [{"value": "CATTLE_001"}],
                "custom": {"sample_name": {"value": "CATTLE_002"}}
            }
        ]
    }

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

    # Validate using the complete validator
    result = validate_organisms_for_django(json_data, structure, action='new')

    print(f"Submission status: {result['submission_status']}")
    print(f"\nValidation results:")
    print(json.dumps(result['validation_results'], indent=2))