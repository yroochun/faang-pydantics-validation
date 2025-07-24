from pydantic import ValidationError
from typing import List, Optional, Dict, Any, Tuple
import json
from organism_validator_classes import OntologyValidator, BreedSpeciesValidator, RelationshipValidator

from organism_ruleset import (
    FAANGOrganismSample
)

class PydanticValidator:
    def __init__(self, schema_file_path: str = None):
        self.relationship_validator = RelationshipValidator()
        self.ontology_validator = OntologyValidator(cache_enabled=True)
        self.breed_validator = BreedSpeciesValidator(self.ontology_validator)
        self.schema_file_path = schema_file_path or "faang_samples_organism.metadata_rules.json"
        self._schema = None


    def validate_organism_sample(
        self,
        data: Dict[str, Any],
        validate_relationships: bool = True,
        validate_ontologies: bool = True,
        validate_with_json_schema: bool = True
    ) -> Tuple[Optional[FAANGOrganismSample], Dict[str, List[str]]]:

        errors_dict = {
            'errors': [],
            'warnings': [],
            'field_errors': {}
        }

        # pydantic validation
        try:
            organism_model = FAANGOrganismSample(**data)
        except ValidationError as e:
            for error in e.errors():
                field_path = '.'.join(str(x) for x in error['loc'])
                error_msg = error['msg']

                if field_path not in errors_dict['field_errors']:
                    errors_dict['field_errors'][field_path] = []
                errors_dict['field_errors'][field_path].append(error_msg)
                errors_dict['errors'].append(f"{field_path}: {error_msg}")

            return None, errors_dict
        except Exception as e:
            errors_dict['errors'].append(str(e))
            return None, errors_dict

        # elixir validation
        if validate_with_json_schema:
            try:
                if self._schema is None:
                    print("Loading organism schema...")
                    with open(self.schema_file_path, 'r') as f:
                        self._schema = json.load(f)

                elixir_results = self.ontology_validator.validate_with_elixir(data, self._schema)

                for vr in elixir_results:
                    path = vr.field_path.lstrip('/')
                    for msg in vr.errors:
                        errors_dict['field_errors'].setdefault(path, []).append(msg)
                        errors_dict['errors'].append(f"{path}: {msg}")

            except Exception as e:
                print(f"JSON Schema validation error: {e}")
                errors_dict['warnings'].append(f"JSON Schema validation skipped due to error: {e}")

        # recommended fields
        recommended_fields = ['birth_date', 'breed', 'health_status']
        for field in recommended_fields:
            if getattr(organism_model, field, None) is None:
                errors_dict['warnings'].append(
                    f"Field '{field}' is recommended but was not provided"
                )

        # ontology validation
        if validate_ontologies:
            ontology_errors = self.validate_ontologies(organism_model)
            errors_dict['errors'].extend(ontology_errors)

        return organism_model, errors_dict

    def validate_ontologies(self, model: FAANGOrganismSample) -> List[str]:
        errors = []

        if model.organism.term != "restricted access":
            if not model.organism.term.startswith("NCBITaxon:"):
                errors.append(f"Organism term '{model.organism.term}' should be from NCBITaxon ontology")

        if model.sex.term != "restricted access":
            if not model.sex.term.startswith("PATO:"):
                errors.append(f"Sex term '{model.sex.term}' should be from PATO ontology")

        if model.breed and model.organism:
            breed_errors = self.breed_validator.validate_breed_for_species(
                model.organism.term,
                model.breed.term
            )
            if breed_errors:
                errors.append(
                    f"Breed '{model.breed.text}' doesn't match the animal "
                    f"specie: '{model.organism.text}'"
                )

        # validate breed against species
        if model.breed and model.organism:
            breed_errors = self.breed_validator.validate_breed_for_species(
                model.organism.term,
                model.breed.term
            )
            if breed_errors:
                errors.append(
                    f"Breed '{model.breed.text}' doesn't match the animal "
                    f"specie: '{model.organism.text}'"
                )

        # validate health status
        if model.health_status:
            for i, status in enumerate(model.health_status):
                if status.term not in ["not applicable", "not collected", "not provided", "restricted access"]:
                    if not (status.term.startswith("PATO:") or status.term.startswith("EFO:")):
                        errors.append(
                            f"Health status[{i}] term '{status.term}' should be from PATO or EFO ontology"
                        )

        return errors

    def validate_organism_relationships(
        self,
        model: FAANGOrganismSample,
        sample_name: str
    ) -> List[str]:
        errors = []

        if not model.child_of:
            return errors

        # max 2 parents
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

        # validate organisms
        for i, org_data in enumerate(organisms):
            sample_name = org_data.get('custom', {}).get('sample_name', {}).get('value', f'organism_{i}')

            model, errors = self.validate_organism_sample(
                org_data,
                validate_relationships=False
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

        # validate relationships
        if results['valid_organisms']:
            relationship_errors = self.validate_relationships(
                [org['model'] for org in results['valid_organisms']],
                organisms
            )

            # relationship errors
            for sample_name, errors in relationship_errors.items():
                for org in results['valid_organisms']:
                    if org['sample_name'] == sample_name:
                        if 'relationship_errors' not in org:
                            org['relationship_errors'] = []
                        org['relationship_errors'].extend(errors)
                        break

        return results

    def validate_relationships(
        self,
        models: List[FAANGOrganismSample],
        raw_data: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        errors_by_sample = {}

        sample_map = {}
        for i, (model, data) in enumerate(zip(models, raw_data)):
            sample_name = data.get('custom', {}).get('sample_name', {}).get('value', f'organism_{i}')
            sample_map[sample_name] = model

        # organism relationships
        for sample_name, model in sample_map.items():
            if not model.child_of:
                continue

            sample_errors = []

            if len(model.child_of) > 2:
                sample_errors.append(f"Organism can have at most 2 parents, found {len(model.child_of)}")

            for parent_ref in model.child_of:
                parent_id = parent_ref.value

                if parent_id == "restricted access":
                    continue

                if parent_id in sample_map:
                    parent_model = sample_map[parent_id]

                    # check species match
                    if model.organism.text != parent_model.organism.text:
                        sample_errors.append(
                            f"Species mismatch: child is '{model.organism.text}' "
                            f"but parent '{parent_id}' is '{parent_model.organism.text}'"
                        )

                    # circular relationships
                    if parent_model.child_of:
                        for grandparent in parent_model.child_of:
                            if grandparent.value == sample_name:
                                sample_errors.append(
                                    f"Circular relationship detected: '{parent_id}' "
                                    f"lists '{sample_name}' as its parent"
                                )
                else:
                    sample_errors.append(
                        f"Parent '{parent_id}' not found in current batch"
                    )

            if sample_errors:
                errors_by_sample[sample_name] = sample_errors

        return errors_by_sample

def export_organism_to_biosample_format(model: FAANGOrganismSample) -> Dict[str, Any]:
    biosample_data = {
        "characteristics": {}
    }

    biosample_data["characteristics"]["material"] = [{
        "text": model.material.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.material.term.replace(':', '_')}"]
    }]

    biosample_data["characteristics"]["organism"] = [{
        "text": model.organism.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.organism.term.replace(':', '_')}"]
    }]

    biosample_data["characteristics"]["sex"] = [{
        "text": model.sex.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.sex.term.replace(':', '_')}"]
    }]

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
            # for error in org['errors']['errors']:
            #     report.append(f"  ERROR: {error}")
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

    def has_issues(record: Dict[str, Any]) -> bool:
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

    for record_type, records in validation_results.items():
        for record in records:
            if has_issues(record):
                return 'Fix issues'

    return 'Ready for submission'


if __name__ == "__main__":

    json_string = """
    {
        "organism": [
            {
                "sample_description": {
                    "value": "Adult female, 23.5 months of age, Thoroughbred"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Foal, 9 days old, Thoroughbred"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Whole embryo, 34 days gestational age, Thoroughbred"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Endometrium (pregnant day 16)"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Endometrium (pregnant day 50)"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Adult male, 4 years of age, Thoroughbred"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Adult"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Adult, Thoroughbred"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Full term, Thoroughbred"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Adult"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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
                "sample_description": {
                    "value": "Foal"
                },
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026"
                },
                "project": {
                    "value": "FAANG"
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

    data = json.loads(json_string)
    sample_organisms = data["organism"]

    validator = PydanticValidator("../rulesets-json/faang_samples_organism.metadata_rules.json")
    results = validator.validate_with_pydantic(sample_organisms)

    report = generate_validation_report(results)
    print(report)

    # export to BioSamples format
    if results['valid_organisms']:
        for valid_org in results['valid_organisms']:
            biosample_data = export_organism_to_biosample_format(valid_org['model'])
            # print(f"\nBioSample format for {valid_org['sample_name']}:")
            # print(json.dumps(biosample_data, indent=2))