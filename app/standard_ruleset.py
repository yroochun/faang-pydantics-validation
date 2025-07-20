from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, List, Literal, Union
from enum import Enum
import json

# dcc-metadata/master/json_schema/core/samples/faang_samples_core.metadata_rules.json
class MaterialValidValues(str, Enum):
    ORGANISM = "organism"
    SPECIMEN_FROM_ORGANISM = "specimen from organism"
    CELL_SPECIMEN = "cell specimen"
    SINGLE_CELL_SPECIMEN = "single cell specimen"
    POOL_OF_SPECIMENS = "pool of specimens"
    CELL_CULTURE = "cell culture"
    CELL_LINE = "cell line"
    ORGANOID = "organoid"
    RESTRICTED_ACCESS = "restricted access"


class MaterialValidTerms(str, Enum):
    OBI_0100026 = "OBI:0100026"  # organism
    OBI_0001479 = "OBI:0001479"  # specimen from organism
    OBI_0001468 = "OBI:0001468"  # cell specimen
    OBI_0002127 = "OBI:0002127"  # single cell specimen
    OBI_0302716 = "OBI:0302716"  # pool of specimens
    OBI_0001876 = "OBI:0001876"  # cell culture
    CLO_0000031 = "CLO:0000031"  # cell line
    NCIT_C172259 = "NCIT:C172259"  # organoid
    RESTRICTED_ACCESS = "restricted access"


class SecondaryProjectValidValues(str, Enum):
    AQUA_FAANG = "AQUA-FAANG"
    BOVREG = "BovReg"
    GENE_SWITCH = "GENE-SWitCH"
    BOVINE_FAANG = "Bovine-FAANG"
    EFFICACE = "EFFICACE"
    GERONIMO = "GEroNIMO"
    RUMIGEN = "RUMIGEN"
    EQUINE_FAANG = "Equine-FAANG"
    HOLORUMINANT = "Holoruminant"
    USPIGFAANG = "USPIGFAANG"


class SampleDescription(BaseModel):
    value: Optional[str] = Field(None, description="A brief description of the sample including species name")


class Material(BaseModel):
    text: MaterialValidValues = Field(..., description="The type of material being described")
    term: MaterialValidTerms = Field(..., description="The ontology term for the material")
    ontology_name: Literal["OBI"] = "OBI"
    _comment: Optional[str] = Field(
        default="Covers organism, specimen from organism, cell specimen, pool of specimens, cell culture, cell line, organoid.",
        alias="_comment"
    )

    # Validate that text and term are consistent
    @validator('term')
    def validate_text_term_consistency(cls, v, values):
        if 'text' not in values:
            return v

        # mapping between text and term
        text_term_mapping = {
            MaterialValidValues.ORGANISM: MaterialValidTerms.OBI_0100026,
            MaterialValidValues.SPECIMEN_FROM_ORGANISM: MaterialValidTerms.OBI_0001479,
            MaterialValidValues.CELL_SPECIMEN: MaterialValidTerms.OBI_0001468,
            MaterialValidValues.SINGLE_CELL_SPECIMEN: MaterialValidTerms.OBI_0002127,
            MaterialValidValues.POOL_OF_SPECIMENS: MaterialValidTerms.OBI_0302716,
            MaterialValidValues.CELL_CULTURE: MaterialValidTerms.OBI_0001876,
            MaterialValidValues.CELL_LINE: MaterialValidTerms.CLO_0000031,
            MaterialValidValues.ORGANOID: MaterialValidTerms.NCIT_C172259,
            MaterialValidValues.RESTRICTED_ACCESS: MaterialValidTerms.RESTRICTED_ACCESS,
        }

        expected_term = text_term_mapping.get(values['text'])
        if expected_term and v != expected_term:
            raise ValueError(f"Term '{v}' does not match text '{values['text']}'. Expected term: '{expected_term}'")

        return v


class Project(BaseModel):
    value: Literal["FAANG"] = Field("FAANG", description="State that the project is 'FAANG'")


class SecondaryProject(BaseModel):
    value: Optional[SecondaryProjectValidValues] = Field(None, description="Secondary project name")


class Availability(BaseModel):
    value: HttpUrl = Field(..., description="Link to web page or email address (with mailto: prefix)")

    @validator('value')
    def validate_availability_format(cls, v):
        url_str = str(v)
        if not (url_str.startswith('http://') or url_str.startswith('https://') or url_str.startswith('mailto:')):
            raise ValueError("Availability must be a web URL or email address with 'mailto:' prefix")
        return v


class SameAs(BaseModel):
    value: Optional[str] = Field(None, description="BioSample ID for an equivalent sample record")


class SampleCoreMetadata(BaseModel):
    # Required fields
    material: Material = Field(..., description="The type of material being described")
    project: Project = Field(..., description="State that the project is 'FAANG'")

    # Optional fields
    describedBy: Optional[
        Literal["https://github.com/FAANG/faang-metadata/blob/master/docs/faang_sample_metadata.md"]] = None
    schema_version: Optional[str] = Field(
        None,
        regex=r"^[0-9]{1,}\.[0-9]{1,}\.[0-9]{1,}$",
        description="The version number of the schema in major.minor.patch format",
        example="4.6.1"
    )
    sample_description: Optional[SampleDescription] = Field(
        None,
        description="Optional: A brief description of the sample including species name"
    )
    availability: Optional[Availability] = Field(
        None,
        description="Optional: Link to web page or email for sample availability"
    )
    same_as: Optional[SameAs] = Field(
        None,
        description="Optional: BioSample ID for equivalent sample record"
    )
    secondary_project: Optional[List[SecondaryProject]] = Field(
        None,
        description="Optional: List of secondary projects this data belongs to"
    )

    # pydantic config
    class Config:
        # Allow field aliases
        allow_population_by_field_name = True
        # Generate schema with examples
        schema_extra = {
            "example": {
                "material": {
                    "text": "organism",
                    "term": "OBI:0100026",
                    "ontology_name": "OBI"
                },
                "project": {
                    "value": "FAANG"
                },
                "sample_description": {
                    "value": "Liver tissue from adult female cattle"
                },
                "schema_version": "4.6.1"
            }
        }


# Validation function for individual samples
def validate_sample_core(data: dict) -> SampleCoreMetadata:
    try:
        return SampleCoreMetadata(**data)
    except Exception as e:
        raise e


def validate_organism_list(organism_list: List[dict]) -> dict:
    validated_organisms = []
    failed_organisms = []

    print(f"Validating {len(organism_list)} organisms...")

    for i, organism in enumerate(organism_list):
        try:
            # Extract the samples_core metadata
            if 'samples_core' not in organism:
                failed_organisms.append({
                    'index': i,
                    'error': 'Missing samples_core section',
                    'sample_name': organism.get('custom', {}).get('sample_name', {}).get('value', f'Organism_{i}')
                })
                continue

            samples_core = organism['samples_core']

            # Validate the core metadata
            validated_sample = validate_sample_core(samples_core)

            # Get sample name for reporting
            sample_name = organism.get('custom', {}).get('sample_name', {}).get('value', f'Organism_{i}')

            validated_organisms.append({
                'index': i,
                'sample_name': sample_name,
                'validated_data': validated_sample.dict()
            })

            print(f"✅ Organism {i} ({sample_name}): Valid")

        except Exception as e:
            sample_name = organism.get('custom', {}).get('sample_name', {}).get('value', f'Organism_{i}')
            failed_organisms.append({
                'index': i,
                'sample_name': sample_name,
                'error': str(e)
            })
            print(f"❌ Organism {i} ({sample_name}): {e}")

    # Summary
    total_organisms = len(organism_list)
    successful_validations = len(validated_organisms)
    failed_validations = len(failed_organisms)

    print(f"\n📊 Validation Summary:")
    print(f"Total organisms: {total_organisms}")
    print(f"Successfully validated: {successful_validations}")
    print(f"Failed validation: {failed_validations}")
    print(f"Success rate: {(successful_validations / total_organisms) * 100:.1f}%")

    return {
        'success': failed_validations == 0,
        'total_organisms': total_organisms,
        'successful_validations': successful_validations,
        'failed_validations': failed_validations,
        'validated_organisms': validated_organisms,
        'failed_organisms': failed_organisms
    }
