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
from ontology_validator import OntologyValidator, ValidationResult
from breed_species_validator import BreedSpeciesValidator



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


class PydanticValidator:
    """Validator that primarily uses Pydantic models with JSON schema as fallback"""

    def __init__(self):
        self.relationship_validator = RelationshipValidator()
        self.ontology_validator = OntologyValidator(cache_enabled=True)
        self.breed_validator = BreedSpeciesValidator(self.ontology_validator)  # Add this
        self.schema_cache = SchemaCache()
        self.json_schema_url = ("https://raw.githubusercontent.com/FAANG/dcc-metadata/master/json_schema/type/"
                                "samples/faang_samples_organism.metadata_rules.json")
        self._resolved_schema = None  # Cache for resolved schema


    def validate_organism_sample(
        self,
        data: Dict[str, Any],
        validate_relationships: bool = True,
        validate_ontologies: bool = True,
        validate_with_json_schema: bool = True  # Add flag to control JSON schema validation
    ) -> Tuple[Optional[FAANGOrganismSample], Dict[str, List[str]]]:

        errors_dict = {
            'errors': [],
            'warnings': [],
            'field_errors': {}
        }

        # 1. Pydantic validation
        try:
            organism_model = FAANGOrganismSample(**data)
        except ValidationError as e:
            # Convert Pydantic errors to a more user-friendly format
            for error in e.errors():
                field_path = '.'.join(str(x) for x in error['loc'])
                error_msg = error['msg']

                if field_path not in errors_dict['field_errors']:
                    errors_dict['field_errors'][field_path] = []
                errors_dict['field_errors'][field_path].append(error_msg)
                errors_dict['errors'].append(f"{field_path}: {error_msg}")

            return None, errors_dict

        # 2. JSON Schema validation with Elixir (if enabled)
        if validate_with_json_schema and self.json_schema_url:
            try:
                # Get and resolve schema only once
                if self._resolved_schema is None:
                    print("Loading and resolving organism schema...")
                    schema = self.schema_cache.get_schema(self.json_schema_url)
                    # Resolve $ref references
                    self._resolved_schema = self.ontology_validator.resolve_schema_refs(schema)

                # Validate with resolved schema
                elixir_results = self.ontology_validator.validate_with_elixir(data, self._resolved_schema)

                for vr in elixir_results:
                    # vr.field_path is a JSON-pointer like "/sex/term"
                    # strip leading slash for readability:
                    path = vr.field_path.lstrip('/')
                    for msg in vr.errors:
                        errors_dict['field_errors'].setdefault(path, []).append(msg)
                        errors_dict['errors'].append(f"{path}: {msg}")

            except Exception as e:
                print(f"JSON Schema validation error: {e}")
                # Don't fail the entire validation if JSON schema validation fails
                errors_dict['warnings'].append(f"JSON Schema validation skipped due to error: {e}")

        # 3. Check recommended fields
        recommended_fields = ['birth_date', 'breed', 'health_status']
        for field in recommended_fields:
            if getattr(organism_model, field, None) is None:
                errors_dict['warnings'].append(
                    f"Field '{field}' is recommended but was not provided"
                )

        # 4. Ontology validation (if enabled)
        if validate_ontologies:
            ontology_errors = self._validate_ontologies(organism_model)
            errors_dict['errors'].extend(ontology_errors)

        # 5. Relationship validation (if enabled)
        if validate_relationships and hasattr(organism_model, 'child_of') and organism_model.child_of:
            rel_errors = self._validate_relationships_for_single(
                organism_model, data.get('custom', {}).get('sample_name', {}).get('value', 'unknown')
            )
            errors_dict['errors'].extend(rel_errors)

        return organism_model, errors_dict

    def _validate_ontologies(self, model: FAANGOrganismSample, data: Dict[str, Any]) -> List[str]:
        """Enhanced ontology validation using Pydantic model data"""
        errors = []

        # Validate organism term
        if model.organism.term != "restricted access":
            # Here you could check against NCBITaxon:1 subclasses
            # For now, just check format
            if not model.organism.term.startswith("NCBITaxon:"):
                errors.append(f"Organism term '{model.organism.term}' should be from NCBITaxon ontology")

        # Validate sex term
        if model.sex.term != "restricted access":
            if not model.sex.term.startswith("PATO:"):
                errors.append(f"Sex term '{model.sex.term}' should be from PATO ontology")

        # Validate breed against species - EXACTLY like Django
        if model.breed and model.organism:
            breed_errors = self.breed_validator.validate_breed_for_species(
                model.organism.term,
                model.breed.term
            )
            if breed_errors:
                # Django adds this specific error to organism field
                errors.append(
                    f"Breed '{model.breed.text}' doesn't match the animal "
                    f"specie: '{model.organism.text}'"
                )

        # Validate breed against species - EXACTLY like Django
        if model.breed and model.organism:
            breed_errors = self.breed_validator.validate_breed_for_species(
                model.organism.term,
                model.breed.term
            )
            if breed_errors:
                # Django adds this specific error to organism field
                errors.append(
                    f"Breed '{model.breed.text}' doesn't match the animal "
                    f"specie: '{model.organism.text}'"
                )

        # Validate health status if present
        if model.health_status:
            for i, status in enumerate(model.health_status):
                if status.term not in ["not applicable", "not collected", "not provided", "restricted access"]:
                    if not (status.term.startswith("PATO:") or status.term.startswith("EFO:")):
                        errors.append(
                            f"Health status[{i}] term '{status.term}' should be from PATO or EFO ontology"
                        )

        return errors

    def _validate_relationships_for_single(
        self,
        model: FAANGOrganismSample,
        sample_name: str
    ) -> List[str]:
        """Validate relationships for a single organism"""
        errors = []

        if not model.child_of:
            return errors

        # Check max 2 parents
        if len(model.child_of) > 2:
            errors.append(f"Organism can have at most 2 parents, found {len(model.child_of)}")

        # Additional relationship checks would go here
        # (checking parent existence, species match, etc.)

        return errors

    def validate_with_pydantic(
        self,
        organisms: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        results = {
            'valid_organisms': [],
            'invalid_organisms': [],
            'summary': {
                'total': len(organisms),
                'valid': 0,
                'invalid': 0,
                'warnings': 0
            }
        }

        # First pass: validate each organism
        for i, org_data in enumerate(organisms):
            sample_name = org_data.get('custom', {}).get('sample_name', {}).get('value', f'organism_{i}')

            model, errors = self.validate_organism_sample(
                org_data,
                validate_relationships=False  # Do relationships in second pass
            )

            if model and not errors['errors']:
                results['valid_organisms'].append({
                    'index': i,
                    'sample_name': sample_name,
                    'model': model,
                    'warnings': errors['warnings']
                })
                results['summary']['valid'] += 1
                if errors['warnings']:
                    results['summary']['warnings'] += 1
            else:
                results['invalid_organisms'].append({
                    'index': i,
                    'sample_name': sample_name,
                    'errors': errors
                })
                results['summary']['invalid'] += 1

        # Second pass: validate relationships across all organisms
        if results['valid_organisms']:
            relationship_errors = self._validate_relationships(
                [org['model'] for org in results['valid_organisms']],
                organisms
            )

            # Apply relationship errors
            for sample_name, errors in relationship_errors.items():
                for org in results['valid_organisms']:
                    if org['sample_name'] == sample_name:
                        if 'relationship_errors' not in org:
                            org['relationship_errors'] = []
                        org['relationship_errors'].extend(errors)
                        break

        return results

    def _validate_relationships(
        self,
        models: List[FAANGOrganismSample],
        raw_data: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Validate relationships across all organisms in a batch"""
        errors_by_sample = {}

        # Create a map of sample names to models
        sample_map = {}
        for i, (model, data) in enumerate(zip(models, raw_data)):
            sample_name = data.get('custom', {}).get('sample_name', {}).get('value', f'organism_{i}')
            sample_map[sample_name] = model

        # Check each organism's relationships
        for sample_name, model in sample_map.items():
            if not model.child_of:
                continue

            sample_errors = []

            for parent_ref in model.child_of:
                parent_id = parent_ref.value

                if parent_id == "restricted access":
                    continue

                # Check if parent exists in current batch
                if parent_id in sample_map:
                    parent_model = sample_map[parent_id]

                    # Check species match
                    if model.organism.text != parent_model.organism.text:
                        sample_errors.append(
                            f"Species mismatch: child is '{model.organism.text}' "
                            f"but parent '{parent_id}' is '{parent_model.organism.text}'"
                        )

                    # Check for circular relationships
                    if parent_model.child_of:
                        for grandparent in parent_model.child_of:
                            if grandparent.value == sample_name:
                                sample_errors.append(
                                    f"Circular relationship detected: '{parent_id}' "
                                    f"lists '{sample_name}' as its parent"
                                )
                else:
                    # Parent not in current batch - would need to check BioSamples
                    sample_errors.append(
                        f"Parent '{parent_id}' not found in current batch"
                    )

            if sample_errors:
                errors_by_sample[sample_name] = sample_errors

        return errors_by_sample


# Utility functions for working with Pydantic models

def export_organism_to_biosample_format(model: FAANGOrganismSample) -> Dict[str, Any]:
    """Convert Pydantic model to BioSamples submission format"""
    biosample_data = {
        "characteristics": {}
    }

    # Add organism
    biosample_data["characteristics"]["organism"] = [{
        "text": model.organism.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.organism.term.replace(':', '_')}"]
    }]

    # Add sex
    biosample_data["characteristics"]["sex"] = [{
        "text": model.sex.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.sex.term.replace(':', '_')}"]
    }]

    # Add optional fields if present
    if model.birth_date:
        biosample_data["characteristics"]["birth date"] = [{
            "text": model.birth_date.value,
            "unit": model.birth_date.units
        }]

    if model.breed:
        biosample_data["characteristics"]["breed"] = [{
            "text": model.breed.text,
            "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.breed.term.replace(':', '_')}"]
        }]

    # Add relationships
    if model.child_of:
        biosample_data["relationships"] = []
        for parent in model.child_of:
            biosample_data["relationships"].append({
                "type": "child of",
                "target": parent.value
            })

    return biosample_data


def generate_validation_report(validation_results: Dict[str, Any]) -> str:
    report = []
    report.append("FAANG Organism Validation Report")
    report.append("=" * 40)
    report.append(f"\nTotal organisms processed: {validation_results['summary']['total']}")
    report.append(f"Valid organisms: {validation_results['summary']['valid']}")
    report.append(f"Invalid organisms: {validation_results['summary']['invalid']}")
    report.append(f"Organisms with warnings: {validation_results['summary']['warnings']}")

    if validation_results['invalid_organisms']:
        report.append("\n\nValidation Errors:")
        report.append("-" * 20)
        for org in validation_results['invalid_organisms']:
            report.append(f"\nOrganism: {org['sample_name']} (index: {org['index']})")
            for error in org['errors']['errors']:
                report.append(f"  ERROR: {error}")
            for field, field_errors in org['errors']['field_errors'].items():
                for error in field_errors:
                    report.append(f"  ERROR in {field}: {error}")

    if validation_results['valid_organisms']:
        warnings_found = False
        for org in validation_results['valid_organisms']:
            if org.get('warnings') or org.get('relationship_errors'):
                if not warnings_found:
                    report.append("\n\nWarnings and Non-Critical Issues:")
                    report.append("-" * 30)
                    warnings_found = True

                report.append(f"\nOrganism: {org['sample_name']} (index: {org['index']})")
                for warning in org.get('warnings', []):
                    report.append(f"  WARNING: {warning}")
                for error in org.get('relationship_errors', []):
                    report.append(f"  RELATIONSHIP: {error}")

    return "\n".join(report)


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

    # Validate using Pydantic validator
    validator = PydanticValidator()
    results = validator.validate_with_pydantic(sample_organisms)

    # Generate report
    report = generate_validation_report(results)
    print(report)

    # Export to BioSamples format if valid
    if results['valid_organisms']:
        for valid_org in results['valid_organisms']:
            biosample_data = export_organism_to_biosample_format(valid_org['model'])
            # print(f"\nBioSample format for {valid_org['sample_name']}:")
            # print(json.dumps(biosample_data, indent=2))