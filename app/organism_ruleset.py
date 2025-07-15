# dcc-metadata/master/json_schema/type/samples/faang_samples_organism.metadata_rules.json

from pydantic import BaseModel, Field, validator, AnyUrl
from typing import List, Optional, Union, Literal
from enum import Enum
import re

# Import the core metadata model
from standard_ruleset import FAASampleCoreMetadata


class MandatoryLevel(str, Enum):
    MANDATORY = "mandatory"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


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
    mandatory: MandatoryLevel
    ontology_name: str


class Organism(OntologyTerm):
    """NCBI taxon ID of organism"""
    mandatory: Literal[MandatoryLevel.MANDATORY] = MandatoryLevel.MANDATORY
    ontology_name: Literal["NCBITaxon"] = "NCBITaxon"


class Sex(OntologyTerm):
    """Animal sex, described using any child term of PATO_0000047"""
    mandatory: Literal[MandatoryLevel.MANDATORY] = MandatoryLevel.MANDATORY
    ontology_name: Literal["PATO"] = "PATO"


class BirthDate(BaseModel):
    """Birth date, in various formats or special values"""
    value: str
    units: DateUnits
    mandatory: Literal[MandatoryLevel.RECOMMENDED] = MandatoryLevel.RECOMMENDED

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
    """Animal breed, described using the FAANG breed description guidelines"""
    mandatory: Literal[MandatoryLevel.RECOMMENDED] = MandatoryLevel.RECOMMENDED
    ontology_name: Literal["LBO"] = "LBO"
    term: Union[str, Literal["not applicable", "restricted access"]]


class HealthStatus(BaseModel):
    """Health status using terms from PATO or EFO"""
    text: str
    term: Union[str, Literal["not applicable", "not collected", "not provided", "restricted access"]]
    mandatory: Literal[MandatoryLevel.RECOMMENDED] = MandatoryLevel.RECOMMENDED
    ontology_name: Literal["PATO", "EFO"]


class Diet(BaseModel):
    """Organism diet summary"""
    value: str
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class BirthLocation(BaseModel):
    """Name of the birth location"""
    value: str
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class BirthLocationLatitude(BaseModel):
    """Latitude of the birth location in decimal degrees"""
    value: float
    units: Literal["decimal degrees"] = "decimal degrees"
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class BirthLocationLongitude(BaseModel):
    """Longitude of the birth location in decimal degrees"""
    value: float
    units: Literal["decimal degrees"] = "decimal degrees"
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class BirthWeight(BaseModel):
    """Birth weight, in kilograms or grams"""
    value: float
    units: WeightUnits
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class PlacentalWeight(BaseModel):
    """Placental weight, in kilograms or grams"""
    value: float
    units: WeightUnits
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class PregnancyLength(BaseModel):
    """Pregnancy length of time, in days, weeks or months"""
    value: float
    units: TimeUnits
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class DeliveryTimingField(BaseModel):
    """Was pregnancy full-term, early or delayed"""
    value: DeliveryTiming
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class DeliveryEaseField(BaseModel):
    """Did the delivery require assistance"""
    value: DeliveryEase
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class Pedigree(BaseModel):
    """A link to pedigree information for the animal"""
    value: AnyUrl
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class ChildOf(BaseModel):
    """Sample name or Biosample ID for sire/dam"""
    value: str
    mandatory: Literal[MandatoryLevel.OPTIONAL] = MandatoryLevel.OPTIONAL


class FAANGOrganismSample(BaseModel):
    """FAANG organism sample metadata model"""

    # Required fields - samples_core now references the imported core metadata
    samples_core: FAASampleCoreMetadata = Field(
        ...,
        description="Core samples-level information from faang_samples_core.metadata_rules.json"
    )
    organism: Organism
    sex: Sex

    # Optional fields with default descriptions
    describedBy: Optional[str] = Field(
        default="https://github.com/FAANG/faang-metadata/blob/master/docs/faang_sample_metadata.md",
        const=True
    )

    schema_version: Optional[str] = Field(
        default=None,
        regex=r'^[0-9]{1,}\.[0-9]{1,}\.[0-9]{1,}$',
        description="The version number of the schema in major.minor.patch format"
    )

    # Recommended fields
    birth_date: Optional[BirthDate] = None
    breed: Optional[Breed] = None
    health_status: Optional[List[HealthStatus]] = None

    # Optional fields
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
    child_of: Optional[List[ChildOf]] = Field(default=None, min_items=1, max_items=2)

    class Config:
        # Allow extra fields that might be added in the future
        extra = "forbid"
        # Use enum values for serialization
        use_enum_values = True
        # Validate assignment
        validate_assignment = True


# Validation function for organism samples
def validate_organism_sample(data: dict) -> FAANGOrganismSample:
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


# Example usage and validation
if __name__ == "__main__":
    # Example of creating a valid organism sample
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
            "mandatory": "mandatory",
            "ontology_name": "NCBITaxon"
        },
        "sex": {
            "text": "female",
            "term": "PATO:0000383",
            "mandatory": "mandatory",
            "ontology_name": "PATO"
        },
        "birth_date": {
            "value": "2020-03-15",
            "units": "YYYY-MM-DD",
            "mandatory": "recommended"
        },
        "breed": {
            "text": "Holstein",
            "term": "LBO:0000001",
            "mandatory": "recommended",
            "ontology_name": "LBO"
        },
        "health_status": [
            {
                "text": "normal",
                "term": "PATO:0000461",
                "mandatory": "recommended",
                "ontology_name": "PATO"
            }
        ]
    }

    try:
        sample = validate_organism_sample(sample_data)
        print("Organism sample created successfully!")
        print(sample.json(indent=2))
    except Exception as e:
        print(f"Validation error: {e}")