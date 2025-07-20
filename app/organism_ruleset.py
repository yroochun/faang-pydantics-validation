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


class OntologyTerm(BaseModel):
    """Base model for ontology terms"""
    text: str
    term: Union[str, Literal["restricted access"]]
    ontology_name: str


class Organism(OntologyTerm):
    ontology_name: Literal["NCBITaxon"] = "NCBITaxon"


class Sex(OntologyTerm):
    """Animal sex, described using any child term of PATO_0000047 - REQUIRED"""
    ontology_name: Literal["PATO"] = "PATO"


class BirthDate(BaseModel):
    value: str
    units: DateUnits

    @validator('value')
    def validate_birth_date(cls, v, values):
        """Validate birth date format"""
        if v in ["not applicable", "not collected", "not provided", "restricted access"]:
            return v

        # Check date patterns
        patterns = [
            r'^[12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$',  # YYYY-MM-DD
            r'^[12]\d{3}-(0[1-9]|1[0-2])$',  # YYYY-MM
            r'^[12]\d{3}$'  # YYYY
        ]

        if not any(re.match(pattern, v) for pattern in patterns):
            raise ValueError(f"Invalid birth date format: {v}")

        return v


class Breed(OntologyTerm):
    """Animal breed, described using the FAANG breed description guidelines - RECOMMENDED"""
    ontology_name: Literal["LBO"] = "LBO"
    term: Union[str, Literal["not applicable", "restricted access"]]


class HealthStatus(BaseModel):
    """Health status using terms from PATO or EFO - RECOMMENDED"""
    text: str
    term: Union[str, Literal["not applicable", "not collected", "not provided", "restricted access"]]
    ontology_name: Literal["PATO", "EFO"]


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

    class Config:
        extra = "forbid"
        use_enum_values = True
        validate_assignment = True


# Validation function for organism samples
def validate_faang_organism_sample(data: dict) -> FAANGOrganismSample:
    """
    Validate FAANG organism sample data against the Pydantic model

    Args:
        data: Dictionary containing organism sample metadata

    Returns:
        Validated FAANGOrganismSample instance

    Raises:
        ValidationError: If data doesn't conform to the schema
    """
    try:
        return FAANGOrganismSample(**data)
    except Exception as e:
        raise e


# Utility function to get field requirement levels
def get_field_requirements() -> dict:
    """Return a mapping of field names to their requirement levels"""
    return {
        # Required fields
        "samples_core": "required",
        "organism": "required",
        "sex": "required",

        # Recommended fields
        "birth_date": "recommended",
        "breed": "recommended",
        "health_status": "recommended",

        # Optional fields
        "diet": "optional",
        "birth_location": "optional",
        "birth_location_latitude": "optional",
        "birth_location_longitude": "optional",
        "birth_weight": "optional",
        "placental_weight": "optional",
        "pregnancy_length": "optional",
        "delivery_timing": "optional",
        "delivery_ease": "optional",
        "pedigree": "optional",
        "child_of": "optional",
    }


# Example usage and validation
if __name__ == "__main__":
    # Example of creating a valid organism sample (without mandatory fields)
    sample_data = {
        "samples_core": {
            "material": {
                "text": "organism",
                "term": "OBI:0100026",
                "ontology_name": "OBI"
            },
            "project": {
                "value": "FAANG"
            },
            "sample_description": {
                "value": "Adult female Holstein cattle from dairy farm"
            },
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
        },
        "birth_date": {
            "value": "2020-03-15",
            "units": "YYYY-MM-DD"
        },
        "breed": {
            "text": "Holstein",
            "term": "LBO:0000001",
            "ontology_name": "LBO"
        },
        "health_status": [
            {
                "text": "normal",
                "term": "PATO:0000461",
                "ontology_name": "PATO"
            }
        ]
    }

    try:
        sample = validate_faang_organism_sample(sample_data)
        print("Organism sample created successfully!")
        print(sample.json(indent=2))

        # Show field requirements
        print("\nField requirement levels:")
        requirements = get_field_requirements()
        for field, level in requirements.items():
            print(f"  {field}: {level}")

    except Exception as e:
        print(f"Validation error: {e}")