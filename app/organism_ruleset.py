# dcc-metadata/master/json_schema/type/samples/faang_samples_organism.metadata_rules.json

from pydantic import BaseModel, Field, validator, AnyUrl
from typing import List, Optional, Union, Literal
from enum import Enum
import re

from standard_ruleset import SampleCoreMetadata


class DateUnits(str, Enum):
    YYYY_MM_DD = "YYYY-MM-DD"
    YYYY_MM = "YYYY-MM"
    YYYY = "YYYY"
    NOT_APPLICABLE = "not applicable"
    NOT_COLLECTED = "not collected"
    NOT_PROVIDED = "not provided"
    RESTRICTED_ACCESS = "restricted access"


class WeightUnits(str, Enum):
    KILOGRAMS = "kilograms"
    GRAMS = "grams"


class TimeUnits(str, Enum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class DeliveryTiming(str, Enum):
    EARLY_PARTURITION = "early parturition"
    FULL_TERM_PARTURITION = "full-term parturition"
    DELAYED_PARTURITION = "delayed parturition"


class DeliveryEase(str, Enum):
    NORMAL_AUTONOMOUS_DELIVERY = "normal autonomous delivery"
    C_SECTION = "c-section"
    VETERINARIAN_ASSISTED = "veterinarian assisted"


# Base ontology term model with graph restriction validation placeholder
class BaseOntologyTerm(BaseModel):
    """Base model for ontology terms with validation placeholders"""
    text: str
    term: str
    ontology_name: Optional[str] = None

    @validator('term')
    def validate_ontology_term(cls, v, values):
        """
        Placeholder for ontological validation.
        In a full implementation, this would validate against the graph restrictions
        defined in the JSON schema using an ontology service or local ontology files.
        """
        if v == "restricted access":
            return v

        # TODO: Implement actual ontological validation
        # This would check against the specific graph_restriction rules
        # defined for each ontology type

        return v


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

    @validator('term')
    def validate_ncbi_taxon(cls, v):
        """Validate NCBI Taxon terms"""
        if v == "restricted access":
            return v

        # TODO: Validate against NCBITaxon:1 subclasses
        # Should check that term is a subclass of NCBITaxon:1
        # using the graph_restriction rules

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

    @validator('term')
    def validate_pato_sex(cls, v):
        """Validate PATO sex terms"""
        if v == "restricted access":
            return v

        # TODO: Validate against PATO:0000047 (biological sex) subclasses
        # Should check that term is a subclass of PATO:0000047

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

    @validator('term')
    def validate_lbo_breed(cls, v):
        """Validate LBO breed terms"""
        if v in ["not applicable", "restricted access"]:
            return v

        # TODO: Validate against LBO:0000000 subclasses
        # Should check that term is a subclass of LBO:0000000

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

    @validator('term')
    def validate_health_status(cls, v):
        """Validate PATO or EFO health status terms"""
        if v in ["not applicable", "not collected", "not provided", "restricted access"]:
            return v

        # TODO: Validate against PATO:0000461 (normal) or EFO:0000408 (disease)
        # Should check that term is a subclass of either root class
        # Note: include_self: true means the root classes themselves are valid

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

class FAANGOrganismSample(BaseModel):
    """FAANG organism sample metadata model

    Field requirement levels:
    - REQUIRED: samples_core, organism, sex
    - RECOMMENDED: birth_date, breed, health_status
    - OPTIONAL: all other fields
    """

    # REQUIRED fields
    samples_core: SampleCoreMetadata = Field(
        ...,
        description="Core samples-level information."
    )
    organism: Organism = Field(..., description="NCBI taxon ID of organism.")
    sex: Sex = Field(..., description="Animal sex, described using any child term of PATO_0000047.")

    # Schema metadata
    describedBy: Optional[str] = Field(
        default="https://github.com/FAANG/faang-metadata/blob/master/docs/faang_sample_metadata.md",
        const=True
    )
    schema_version: Optional[str] = Field(
        default=None,
        regex=r'^[0-9]{1,}\.[0-9]{1,}\.[0-9]{1,}$',
        description="The version number of the schema in major.minor.patch format"
    )

    # RECOMMENDED fields - Optional but encouraged
    birth_date: Optional[BirthDate] = Field(None, description="Birth date, in the format YYYY-MM-DD, or YYYY-MM where "
                                                              "only the month is known. For embryo samples record "
                                                              "'not applicable")
    breed: Optional[Breed] = Field(None, description="Animal breed, described using the FAANG breed description "
                                                     "guidelines (http://bit.ly/FAANGbreed). Should be considered "
                                                     "mandatory for terrestiral species, for aquatic species "
                                                     "record 'not applicable'.")
    health_status: Optional[List[HealthStatus]] = Field(None, description="Healthy animals should have the term normal, "
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
        use_enum_values = True
        validate_assignment = True


# Validation function for organism samples
# Enhanced validation function with graph restriction checking
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
    if validate_ontology:
        # TODO: Implement full ontological validation
        # This would check each ontology term against its graph_restriction rules
        # using an ontology service or local ontology files
        pass

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


# Example usage showing the limitations
if __name__ == "__main__":
    # This example works but doesn't perform full ontological validation
    sample_data = {
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
            "term": "NCBITaxon:9913",  # This should be validated against NCBITaxon:1 subclasses
            "ontology_name": "NCBITaxon"
        },
        "sex": {
            "text": "female",
            "term": "PATO:0000383",  # This should be validated against PATO:0000047 subclasses
            "ontology_name": "PATO"
        }
    }

    try:
        sample = validate_faang_organism_sample(sample_data)
        print("✓ Basic validation passed")
        print("⚠ Note: Full ontological validation not implemented")
        print("\nOntology requirements:")
        for field, reqs in get_ontology_requirements().items():
            print(f"  {field}: {reqs}")

    except Exception as e:
        print(f"✗ Validation error: {e}")