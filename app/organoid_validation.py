from pydantic import ValidationError
from typing import List, Optional, Dict, Any, Tuple
import json
from organism_validator_classes import OntologyValidator, BreedSpeciesValidator, RelationshipValidator

from app.rulesets_pydantics.organoid_ruleset import (
    FAANGOrganoidSample
)


class PydanticValidator:
    def __init__(self, schema_file_path: str = None):
        self.relationship_validator = RelationshipValidator()
        self.ontology_validator = OntologyValidator(cache_enabled=True)
        self.schema_file_path = schema_file_path or "faang_samples_organoid.metadata_rules.json"
        self._schema = None

    def validate_organoid_sample(
        self,
        data: Dict[str, Any],
        validate_relationships: bool = True,
        validate_ontologies: bool = True,
        validate_with_json_schema: bool = True
    ) -> Tuple[Optional[FAANGOrganoidSample], Dict[str, List[str]]]:

        errors_dict = {
            'errors': [],
            'warnings': [],
            'field_errors': {}
        }

        # pydantic validation
        try:
            organoid_model = FAANGOrganoidSample(**data)
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
                    print("Loading organoid schema...")
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
        recommended_fields = ['organ_part_model', 'number_of_frozen_cells',
                              'organoid_culture_and_passage_protocol', 'organoid_morphology']
        for field in recommended_fields:
            if getattr(organoid_model, field, None) is None:
                errors_dict['warnings'].append(
                    f"Field '{field}' is recommended but was not provided"
                )

        # ontology validation
        if validate_ontologies:
            ontology_errors = self.validate_ontologies(organoid_model)
            errors_dict['errors'].extend(ontology_errors)

        # check for inappropriate missing values
        missing_value_errors = self.check_missing_values(organoid_model)
        errors_dict['errors'].extend(missing_value_errors)

        return organoid_model, errors_dict

    def validate_ontologies(self, model: FAANGOrganoidSample) -> List[str]:
        errors = []

        # Validate organ_model term
        if model.organ_model.term != "restricted access":
            if not (model.organ_model.term.startswith("UBERON:") or
                    model.organ_model.term.startswith("BTO:")):
                errors.append(f"Organ model term '{model.organ_model.term}' should be from UBERON or BTO ontology")

        # Validate organ_part_model if present
        if model.organ_part_model and model.organ_part_model.term != "restricted access":
            if not (model.organ_part_model.term.startswith("UBERON:") or
                    model.organ_part_model.term.startswith("BTO:")):
                errors.append(
                    f"Organ part model term '{model.organ_part_model.term}' should be from UBERON or BTO ontology")

        # Validate freezing date consistency
        if model.freezing_date and model.freezing_date.value != "restricted access":
            import datetime
            date_value = model.freezing_date.value
            date_units = model.freezing_date.units

            if date_units == "YYYY-MM-DD":
                date_format = '%Y-%m-%d'
            elif date_units == "YYYY-MM":
                date_format = '%Y-%m'
            elif date_units == "YYYY":
                date_format = '%Y'
            else:
                return errors

            try:
                datetime.datetime.strptime(date_value, date_format)
            except ValueError:
                errors.append(
                    f"Date units: {date_units} should be consistent with date value: {date_value}"
                )

        return errors

    def check_missing_values(self, model: FAANGOrganoidSample) -> List[str]:
        """Check for inappropriate missing values in mandatory fields"""
        errors = []

        # Define inappropriate missing values for mandatory fields
        inappropriate_values = ["not applicable", "not collected", "not provided"]

        # Check organoid_passage_protocol (mandatory field)
        if hasattr(model.organoid_passage_protocol, 'value'):
            if model.organoid_passage_protocol.value in inappropriate_values:
                errors.append(
                    f"Field 'organoid_passage_protocol' contains missing value '{model.organoid_passage_protocol.value}' "
                    f"that is not appropriate for mandatory fields"
                )

        # Check other mandatory text fields if they have inappropriate missing values
        if hasattr(model.organ_model, 'text'):
            if model.organ_model.text in inappropriate_values:
                errors.append(
                    f"Field 'organ_model' contains missing value '{model.organ_model.text}' "
                    f"that is not appropriate for mandatory fields"
                )

        return errors

    def validate_organoid_relationships(
        self,
        model: FAANGOrganoidSample,
        sample_name: str
    ) -> List[str]:
        errors = []

        if not model.derived_from:
            return errors

        # Organoid-specific relationship validation would go here
        # For example, checking that parent is specimen_from_organism type

        return errors

    def validate_with_pydantic(
        self,
        organoids: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        results = {
            'valid_organoids': [],
            'invalid_organoids': [],
            'summary': {
                'total': len(organoids),
                'valid': 0,
                'invalid': 0,
                'warnings': 0
            }
        }

        # validate organoids
        for i, org_data in enumerate(organoids):
            sample_name = org_data.get('custom', {}).get('sample_name', {}).get('value', f'organoid_{i}')

            model, errors = self.validate_organoid_sample(
                org_data,
                validate_relationships=False
            )

            if model and not errors['errors']:
                results['valid_organoids'].append({
                    'index': i,
                    'sample_name': sample_name,
                    'model': model,
                    'warnings': errors['warnings']
                })
                results['summary']['valid'] += 1
                if errors['warnings']:
                    results['summary']['warnings'] += 1
            else:
                results['invalid_organoids'].append({
                    'index': i,
                    'sample_name': sample_name,
                    'errors': errors
                })
                results['summary']['invalid'] += 1

        # validate relationships
        if results['valid_organoids']:
            relationship_errors = self.validate_relationships(
                [org['model'] for org in results['valid_organoids']],
                organoids
            )

            # relationship errors
            for sample_name, errors in relationship_errors.items():
                for org in results['valid_organoids']:
                    if org['sample_name'] == sample_name:
                        if 'relationship_errors' not in org:
                            org['relationship_errors'] = []
                        org['relationship_errors'].extend(errors)
                        break

        return results

    def validate_relationships(
        self,
        models: List[FAANGOrganoidSample],
        raw_data: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        errors_by_sample = {}

        sample_map = {}
        for i, (model, data) in enumerate(zip(models, raw_data)):
            sample_name = data.get('custom', {}).get('sample_name', {}).get('value', f'organoid_{i}')
            sample_map[sample_name] = model

        # organoid relationships
        for sample_name, model in sample_map.items():
            if not model.derived_from:
                continue

            sample_errors = []

            parent_id = model.derived_from.value

            if parent_id == "restricted access":
                continue

            # Check if parent exists in current batch
            if parent_id not in sample_map and not parent_id.startswith('SAM'):
                sample_errors.append(
                    f"Parent sample '{parent_id}' not found in current batch"
                )

            # For organoids, we should check that parent is specimen_from_organism type
            # This would require additional context about parent samples

            if sample_errors:
                errors_by_sample[sample_name] = sample_errors

        return errors_by_sample


def export_organoid_to_biosample_format(model: FAANGOrganoidSample) -> Dict[str, Any]:
    biosample_data = {
        "characteristics": {}
    }

    # Material
    biosample_data["characteristics"]["material"] = [{
        "text": model.material.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.material.term.replace(':', '_')}"]
    }]

    # Required fields
    biosample_data["characteristics"]["organ model"] = [{
        "text": model.organ_model.text,
        "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.organ_model.term.replace(':', '_')}"]
    }]

    biosample_data["characteristics"]["freezing method"] = [{
        "text": model.freezing_method.value
    }]

    biosample_data["characteristics"]["organoid passage"] = [{
        "text": str(model.organoid_passage.value),
        "unit": model.organoid_passage.units
    }]

    biosample_data["characteristics"]["organoid passage protocol"] = [{
        "text": model.organoid_passage_protocol.value
    }]

    biosample_data["characteristics"]["type of organoid culture"] = [{
        "text": model.type_of_organoid_culture.value
    }]

    biosample_data["characteristics"]["growth environment"] = [{
        "text": model.growth_environment.value
    }]

    # Conditional fields - only include if freezing method is not fresh
    if model.freezing_method.value != "fresh":
        if model.freezing_date:
            biosample_data["characteristics"]["freezing date"] = [{
                "text": model.freezing_date.value,
                "unit": model.freezing_date.units
            }]

        if model.freezing_protocol:
            biosample_data["characteristics"]["freezing protocol"] = [{
                "text": model.freezing_protocol.value
            }]

    # Optional fields
    if model.organ_part_model:
        biosample_data["characteristics"]["organ part model"] = [{
            "text": model.organ_part_model.text,
            "ontologyTerms": [f"http://purl.obolibrary.org/obo/{model.organ_part_model.term.replace(':', '_')}"]
        }]

    if model.number_of_frozen_cells:
        biosample_data["characteristics"]["number of frozen cells"] = [{
            "text": str(model.number_of_frozen_cells.value),
            "unit": model.number_of_frozen_cells.units
        }]

    if model.organoid_culture_and_passage_protocol:
        biosample_data["characteristics"]["organoid culture and passage protocol"] = [{
            "text": model.organoid_culture_and_passage_protocol.value
        }]

    if model.organoid_morphology:
        biosample_data["characteristics"]["organoid morphology"] = [{
            "text": model.organoid_morphology.value
        }]

    # Relationships
    if model.derived_from:
        biosample_data["relationships"] = [{
            "type": "derived from",
            "target": model.derived_from.value
        }]

    return biosample_data


def generate_validation_report(validation_results: Dict[str, Any]) -> str:
    report = []
    report.append("FAANG Organoid Validation Report")
    report.append("=" * 40)
    report.append(f"\nTotal organoids processed: {validation_results['summary']['total']}")
    report.append(f"Valid organoids: {validation_results['summary']['valid']}")
    report.append(f"Invalid organoids: {validation_results['summary']['invalid']}")
    report.append(f"Organoids with warnings: {validation_results['summary']['warnings']}")

    if validation_results['invalid_organoids']:
        report.append("\n\nValidation Errors:")
        report.append("-" * 20)
        for org in validation_results['invalid_organoids']:
            report.append(f"\nOrganoid: {org['sample_name']} (index: {org['index']})")
            for field, field_errors in org['errors']['field_errors'].items():
                for error in field_errors:
                    report.append(f"  ERROR in {field}: {error}")

    if validation_results['valid_organoids']:
        warnings_found = False
        for org in results['valid_organoids']:
            if org.get('warnings') or org.get('relationship_errors'):
                if not warnings_found:
                    report.append("\n\nWarnings and Non-Critical Issues:")
                    report.append("-" * 30)
                    warnings_found = True

                report.append(f"\nOrganoid: {org['sample_name']} (index: {org['index']})")
                for warning in org.get('warnings', []):
                    report.append(f"  WARNING: {warning}")
                for error in org.get('relationship_errors', []):
                    report.append(f"  RELATIONSHIP: {error}")

    return "\n".join(report)


def get_submission_status(validation_results: Dict[str, Any]) -> str:
    def has_issues(record: Dict[str, Any]) -> bool:
        # Check for errors in invalid organoids
        if 'errors' in record and record['errors']:
            return True

        # Check for relationship errors in valid organoids
        if 'relationship_errors' in record and record['relationship_errors']:
            return True

        return False

    # Check invalid organoids
    for record in validation_results.get('invalid_organoids', []):
        if has_issues(record):
            return 'Fix issues'

    # Check valid organoids for relationship errors
    for record in validation_results.get('valid_organoids', []):
        if has_issues(record):
            return 'Fix issues'

    return 'Ready for submission'


if __name__ == "__main__":

    json_string = """
    {
        "organoid": [
            {
                "sample_description": {
                    "value": "Liver organoid derived from adult liver specimen"
                },
                "material": {
                    "text": "organoid", 
                    "term": "OBI:0002090"
                },
                "project": {
                    "value": "FAANG"
                },
                "organ_model": {
                    "ontology_name": "UBERON",
                    "text": "liver",
                    "term": "UBERON:0002107"
                },
                "organ_part_model": {
                    "ontology_name": "UBERON", 
                    "text": "hepatocyte",
                    "term": "UBERON:0000182"
                },
                "freezing_method": {
                    "value": "frozen, liquid nitrogen"
                },
                "freezing_date": {
                    "value": "2024-03-15",
                    "units": "YYYY-MM-DD"
                },
                "freezing_protocol": {
                    "value": "https://protocols.io/view/organoid-freezing-protocol"
                },
                "number_of_frozen_cells": {
                    "value": 5.0,
                    "units": "organoids"
                },
                "organoid_passage": {
                    "value": 3,
                    "units": "passages"
                },
                "organoid_passage_protocol": {
                    "value": "https://protocols.io/view/organoid-passaging"
                },
                "organoid_culture_and_passage_protocol": {
                    "value": "https://protocols.io/view/organoid-culture"
                },
                "type_of_organoid_culture": {
                    "value": "3D"
                },
                "growth_environment": {
                    "value": "matrigel"
                },
                "organoid_morphology": {
                    "value": "Epithelial monolayer with budding crypt-like domains"
                },
                "derived_from": {
                    "value": "LIVER_SPEC_001"
                },
                "custom": {
                    "sample_name": {
                        "value": "LIVER_ORG_001"
                    }
                }
            },
            {
                "sample_description": {
                    "value": "Kidney organoid fresh sample"
                },
                "material": {
                    "text": "organoid",
                    "term": "OBI:0002090"
                },
                "project": {
                    "value": "FAANG"
                },
                "organ_model": {
                    "ontology_name": "UBERON",
                    "text": "kidney", 
                    "term": "UBERON:0002113"
                },
                "freezing_method": {
                    "value": "fresh"
                },
                "organoid_passage": {
                    "value": 0,
                    "units": "passages"
                },
                "organoid_passage_protocol": {
                    "value": "https://protocols.io/view/kidney-organoid-protocol"
                },
                "type_of_organoid_culture": {
                    "value": "3D"
                },
                "growth_environment": {
                    "value": "liquid suspension"
                },
                "derived_from": {
                    "value": "SAMEA12345678"
                },
                "custom": {
                    "sample_name": {
                        "value": "KIDNEY_ORG_001"
                    }
                }
            },
            {
                "sample_description": {
                    "value": "Brain organoid with errors"
                },
                "material": {
                    "text": "organoid",
                    "term": "OBI:0002090"
                },
                "project": {
                    "value": "FAANG"
                },
                "organ_model": {
                    "ontology_name": "INVALID",
                    "text": "brain",
                    "term": "INVALID:123"
                },
                "freezing_method": {
                    "value": "frozen, -70 freezer"
                },
                "freezing_date": {
                    "value": "2024-03",
                    "units": "YYYY-MM-DD"
                },
                "freezing_protocol": {
                    "value": "https://protocols.io/view/freezing"
                },
                "organoid_passage": {
                    "value": 1,
                    "units": "passages"
                },
                "organoid_passage_protocol": {
                    "value": "not collected"
                },
                "type_of_organoid_culture": {
                    "value": "3D"
                },
                "growth_environment": {
                    "value": "matrigel"
                },
                "derived_from": {
                    "value": "BRAIN_SPEC_001"
                },
                "custom": {
                    "sample_name": {
                        "value": "BRAIN_ORG_001"
                    }
                }
            }
        ]
    }
    """

    data = json.loads(json_string)
    sample_organoids = data["organoid"]

    validator = PydanticValidator("../rulesets-json/faang_samples_organoid.metadata_rules.json")
    results = validator.validate_with_pydantic(sample_organoids)

    report = generate_validation_report(results)
    print(report)

    # export to BioSamples format
    if results['valid_organoids']:
        for valid_org in results['valid_organoids']:
            biosample_data = export_organoid_to_biosample_format(valid_org['model'])
            print(f"\nBioSample format for {valid_org['sample_name']}:")
            print(json.dumps(biosample_data, indent=2))