# dcc-metadata/master/json_schema/type/samples/faang_samples_organism.metadata_rules.json

from pydantic import BaseModel, Field, validator, AnyUrl
from ontology_validator import OntologyValidator, ValidationResult

from typing import List, Optional, Union, Literal
import re

from standard_ruleset import SampleCoreMetadata

# Replace Enums with Literal types
DateUnits = Literal[
    "YYYY-MM-DD",
    "YYYY-MM",
    "YYYY",
    "not applicable",
    "not collected",
    "not provided",
    "restricted access"
]

WeightUnits = Literal["kilograms", "grams"]

TimeUnits = Literal[
    "days",
    "weeks",
    "months",
    "day",
    "week",
    "month"
]

DeliveryTiming = Literal[
    "early parturition",
    "full-term parturition",
    "delayed parturition"
]

DeliveryEase = Literal[
    "normal autonomous delivery",
    "c-section",
    "veterinarian assisted"
]


# Base ontology term model with graph restriction validation placeholder
class BaseOntologyTerm(BaseModel):
    """Base model for ontology terms with validation placeholders"""
    text: str
    term: str
    ontology_name: Optional[str] = None


class Organism(BaseOntologyTerm):
    """
    NCBI taxon ID of organism.
    JSON Schema graph_restriction:
    - ontologies: ["obo:ncbitaxon"]
    - classes: ["NCBITaxon:1"]
    - relations: ["rdfs:subClassOf"]
    - direct: false, include_self: false
    """
    ontology_name: Literal["NCBITaxon"] = "NCBITaxon"
    term: Union[str, Literal["restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_ncbi_taxon(cls, v, values, **kwargs):
        """Validate NCBI Taxon terms"""
        if v == "restricted access":
            return v

        # call out to OLS and enforce subclass of NCBITaxon:1
        ont = values.get('ontology_name', "NCBITaxon")
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["NCBITaxon"]  # top‐level taxon class
        )
        if res.errors:
            raise ValueError(f"Organism term invalid: {res.errors}")
        return v


class Sex(BaseOntologyTerm):
    """
    Animal sex, described using any child term of PATO_0000047 - REQUIRED
    JSON Schema graph_restriction:
    - ontologies: ["obo:pato"]
    - classes: ["PATO:0000047"]
    - relations: ["rdfs:subClassOf"]
    - direct: false, include_self: false
    """
    ontology_name: Literal["PATO"] = "PATO"
    term: Union[str, Literal["restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_pato_sex(cls, v, values, **kwargs):
        """Validate PATO sex terms"""
        if v == "restricted access":
            return v

        ont = values.get('ontology_name')
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["PATO:0000047"]
        )
        if res.errors:
            raise ValueError(f"Sex term invalid: {res.errors}")
        return v


class BirthDate(BaseModel):
    value: str
    units: DateUnits

    @validator('value')
    def validate_birth_date(cls, v, values):
        """Validate birth date format according to JSON schema pattern"""
        if v in ["not applicable", "not collected", "not provided", "restricted access"]:
            return v

        # Pattern from JSON schema: ^[12]\\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])|[12]\\d{3}-(0[1-9]|1[0-2])|[12]\\d{3}$
        pattern = r'^[12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])|[12]\d{3}-(0[1-9]|1[0-2])|[12]\d{3}$'

        if not re.match(pattern, v):
            raise ValueError(f"Invalid birth date format: {v}. Must match YYYY-MM-DD, YYYY-MM, or YYYY pattern")

        return v


class Breed(BaseOntologyTerm):
    """
    Animal breed, described using the FAANG breed description guidelines - RECOMMENDED
    JSON Schema graph_restriction:
    - ontologies: ["obo:lbo"]
    - classes: ["LBO:0000000"]
    - relations: ["rdfs:subClassOf"]
    - direct: false, include_self: false
    """
    ontology_name: Literal["LBO"] = "LBO"
    term: Union[str, Literal["not applicable", "restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_lbo_breed(cls, v, values, **kwargs):
        """Validate LBO breed terms"""
        if v in ["not applicable", "restricted access"]:
            return v

        ont = values.get('ontology_name')
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["LBO"]  # LBO:0000000
        )
        if res.errors:
            raise ValueError(f"Breed term invalid: {res.errors}")

        return v


class HealthStatus(BaseOntologyTerm):
    """
    Health status using terms from PATO or EFO - RECOMMENDED
    JSON Schema graph_restriction:
    - ontologies: ["obo:pato", "obo:efo"]
    - classes: ["PATO:0000461", "EFO:0000408"]
    - relations: ["rdfs:subClassOf"]
    - direct: false, include_self: true
    """
    ontology_name: Optional[Literal["PATO", "EFO"]] = None
    term: Union[str, Literal["not applicable", "not collected", "not provided", "restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_health_status(cls, v, values, **kwargs):
        """Validate PATO or EFO health status terms"""
        if v in ["not applicable", "not collected", "not provided", "restricted access"]:
            return v

        # determine which ontology to use (PATO or EFO)
        ont = values.get('ontology_name', "PATO")
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["PATO:0000461", "EFO:0000408"]
        )
        if res.errors:
            raise ValueError(f"HealthStatus term invalid: {res.errors}")

        return v


class Diet(BaseModel):
    """Organism diet summary, more detailed information will be recorded in the associated protocols.
    Particuarly important for projects with controlled diet treatements.
    Free text field, but ensure standardisation within each study"""
    value: str


class BirthLocation(BaseModel):
    """Name of the birth location - OPTIONAL"""
    value: str


class BirthLocationLatitude(BaseModel):
    """Latitude of the birth location in decimal degrees - OPTIONAL"""
    value: float
    units: Literal["decimal degrees"] = "decimal degrees"


class BirthLocationLongitude(BaseModel):
    """Longitude of the birth location in decimal degrees - OPTIONAL"""
    value: float
    units: Literal["decimal degrees"] = "decimal degrees"


class BirthWeight(BaseModel):
    """Birth weight, in kilograms or grams - OPTIONAL"""
    value: float
    units: WeightUnits


class PlacentalWeight(BaseModel):
    """Placental weight, in kilograms or grams - OPTIONAL"""
    value: float
    units: WeightUnits


class PregnancyLength(BaseModel):
    """Pregnancy length of time, in days, weeks or months - OPTIONAL"""
    value: float
    units: TimeUnits


class DeliveryTimingField(BaseModel):
    """Was pregnancy full-term, early or delayed - OPTIONAL"""
    value: DeliveryTiming


class DeliveryEaseField(BaseModel):
    """Did the delivery require assistance - OPTIONAL"""
    value: DeliveryEase


class Pedigree(BaseModel):
    """A link to pedigree information for the animal - OPTIONAL"""
    value: AnyUrl


class ChildOf(BaseModel):
    """Sample name or Biosample ID for sire/dam - OPTIONAL"""
    value: str


class SampleName(BaseModel):
    value: str


class Custom(BaseModel):
    sample_name: SampleName


class FAANGOrganismSample(SampleCoreMetadata):
    """FAANG organism sample metadata model

    Now inherits from SampleCoreMetadata, which provides:
    - material (REQUIRED)
    - project (REQUIRED)
    - describedBy (OPTIONAL)
    - schema_version (OPTIONAL)
    - sample_description (OPTIONAL)
    - availability (OPTIONAL)
    - same_as (OPTIONAL)
    - secondary_project (OPTIONAL)

    Additional field requirement levels:
    - REQUIRED: organism, sex
    - RECOMMENDED: birth_date, breed, health_status
    - OPTIONAL: all other fields
    """

    # REQUIRED fields specific to organism samples
    organism: Organism = Field(..., description="NCBI taxon ID of organism.")
    sex: Sex = Field(..., description="Animal sex, described using any child term of PATO_0000047.")

    # RECOMMENDED fields - Optional but encouraged
    birth_date: Optional[BirthDate] = Field(None, description="Birth date, in the format YYYY-MM-DD, or YYYY-MM where "
                                                              "only the month is known. For embryo samples record "
                                                              "'not applicable")
    breed: Optional[Breed] = Field(None, description="Animal breed, described using the FAANG breed description "
                                                     "guidelines (http://bit.ly/FAANGbreed). Should be considered "
                                                     "mandatory for terrestiral species, for aquatic species "
                                                     "record 'not applicable'.")
    health_status: Optional[List[HealthStatus]] = Field(None,
                                                        description="Healthy animals should have the term normal, "
                                                                    "otherwise use the as many disease terms as "
                                                                    "necessary from EFO.")

    # OPTIONAL fields
    diet: Optional[Diet] = None
    birth_location: Optional[BirthLocation] = None
    birth_location_latitude: Optional[BirthLocationLatitude] = None
    birth_location_longitude: Optional[BirthLocationLongitude] = None
    birth_weight: Optional[BirthWeight] = None
    placental_weight: Optional[PlacentalWeight] = None
    pregnancy_length: Optional[PregnancyLength] = None
    delivery_timing: Optional[DeliveryTimingField] = None
    delivery_ease: Optional[DeliveryEaseField] = None
    pedigree: Optional[Pedigree] = None
    child_of: Optional[List[ChildOf]] = Field(default=None, min_items=1, max_items=2,
                                              description="Healthy animals should have the term normal, otherwise use "
                                                          "the as many disease terms as necessary from EFO.")
    custom: Optional[Custom] = None

    class Config:
        extra = "forbid"
        validate_all = True
        validate_assignment = True


# Validation function for organism samples
def validate_faang_organism_sample(data: dict, validate_ontology: bool = False) -> FAANGOrganismSample:
    """
    Validate FAANG organism sample data against the Pydantic model

    Args:
        data: Dictionary containing organism sample metadata
        validate_ontology: If True, performs full ontological validation (requires ontology service)

    Returns:
        Validated FAANGOrganismSample instance

    Raises:
        ValidationError: If data doesn't conform to the schema
    """

    # Extract samples_core data if provided separately
    if 'samples_core' in data:
        # Merge samples_core fields into the main data dict
        samples_core = data.pop('samples_core')
        # Add each field from samples_core to the main data
        for key, value in samples_core.items():
            if key not in data:  # Don't overwrite if already present at top level
                data[key] = value

    try:
        return FAANGOrganismSample(**data)
    except Exception as e:
        raise e


def get_ontology_requirements() -> dict:
    """
    Return the ontological requirements for each field based on JSON schema graph_restrictions
    """
    return {
        "organism": {
            "ontologies": ["obo:ncbitaxon"],
            "classes": ["NCBITaxon:1"],
            "relations": ["rdfs:subClassOf"],
            "direct": False,
            "include_self": False,
            "allowed_literals": ["restricted access"]
        },
        "sex": {
            "ontologies": ["obo:pato"],
            "classes": ["PATO:0000047"],
            "relations": ["rdfs:subClassOf"],
            "direct": False,
            "include_self": False,
            "allowed_literals": ["restricted access"]
        },
        "breed": {
            "ontologies": ["obo:lbo"],
            "classes": ["LBO:0000000"],
            "relations": ["rdfs:subClassOf"],
            "direct": False,
            "include_self": False,
            "allowed_literals": ["not applicable", "restricted access"]
        },
        "health_status": {
            "ontologies": ["obo:pato", "obo:efo"],
            "classes": ["PATO:0000461", "EFO:0000408"],
            "relations": ["rdfs:subClassOf"],
            "direct": False,
            "include_self": True,
            "allowed_literals": ["not applicable", "not collected", "not provided", "restricted access"]
        }
    }


# Example usage
if __name__ == "__main__":
    # Example 1: With samples_core as a nested field (backward compatible)
    sample_data_nested = {
        "samples_core": {
            "material": {
                "text": "organism",
                "term": "OBI:0100026",
                "ontology_name": "OBI"
            },
            "project": {"value": "FAANG"},
            "sample_description": {"value": "Adult female Holstein cattle"},
            "schema_version": "4.6.1"
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
        }
    }

    # Example 2: With fields at the top level (cleaner structure)
    sample_data_flat = {
        "material": {
            "text": "organism",
            "term": "OBI:0100026",
            "ontology_name": "OBI"
        },
        "project": {"value": "FAANG"},
        "sample_description": {"value": "Adult female Holstein cattle"},
        "schema_version": "4.6.1",
        "organism": {
            "text": "Bos taurus",
            "term": "NCBITaxon:9913",
            "ontology_name": "NCBITaxon"
        },
        "sex": {
            "text": "female",
            "term": "PATO:0000383",
            "ontology_name": "PATO"
        }
    }

    try:
        # Test nested structure
        print("Testing nested structure...")
        sample1 = validate_faang_organism_sample(sample_data_nested)
        print("✓ Nested structure validation passed")

        # Test flat structure
        print("\nTesting flat structure...")
        sample2 = validate_faang_organism_sample(sample_data_flat)
        print("✓ Flat structure validation passed")

        print("\n⚠ Note: Full ontological validation not implemented")
        print("\nOntology requirements:")
        for field, reqs in get_ontology_requirements().items():
            print(f"  {field}: {reqs}")

    except Exception as e:
        print(f"✗ Validation error: {e}")