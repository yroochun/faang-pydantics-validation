from pydantic import BaseModel, Field, validator, AnyUrl
from ontology_validator import OntologyValidator, ValidationResult
from typing import List, Optional, Union, Literal
import re

from standard_ruleset import SampleCoreMetadata

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

class BaseOntologyTerm(BaseModel):
    text: str
    term: str
    ontology_name: Optional[str] = None


class Organism(BaseOntologyTerm):
    ontology_name: Literal["NCBITaxon"] = "NCBITaxon"
    term: Union[str, Literal["restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_ncbi_taxon(cls, v, values, **kwargs):
        if v == "restricted access":
            return v

        ont = values.get('ontology_name', "NCBITaxon")
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["NCBITaxon"]
        )
        if res.errors:
            raise ValueError(f"Organism term invalid: {res.errors}")
        return v


class Sex(BaseOntologyTerm):
    ontology_name: Literal["PATO"] = "PATO"
    term: Union[str, Literal["restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_pato_sex(cls, v, values, **kwargs):
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
        if v in ["not applicable", "not collected", "not provided", "restricted access"]:
            return v

        pattern = r'^[12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])|[12]\d{3}-(0[1-9]|1[0-2])|[12]\d{3}$'

        if not re.match(pattern, v):
            raise ValueError(f"Invalid birth date format: {v}. Must match YYYY-MM-DD, YYYY-MM, or YYYY pattern")

        return v


class Breed(BaseOntologyTerm):
    ontology_name: Literal["LBO"] = "LBO"
    term: Union[str, Literal["not applicable", "restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_lbo_breed(cls, v, values, **kwargs):
        if v in ["not applicable", "restricted access"]:
            return v

        ont = values.get('ontology_name')
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["LBO"]
        )
        if res.errors:
            raise ValueError(f"Breed term invalid: {res.errors}")

        return v


class HealthStatus(BaseOntologyTerm):
    ontology_name: Optional[Literal["PATO", "EFO"]] = None
    term: Union[str, Literal["not applicable", "not collected", "not provided", "restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_health_status(cls, v, values, **kwargs):
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
    value: str


class BirthLocation(BaseModel):
    value: str


class BirthLocationLatitude(BaseModel):
    value: float
    units: Literal["decimal degrees"] = "decimal degrees"


class BirthLocationLongitude(BaseModel):
    value: float
    units: Literal["decimal degrees"] = "decimal degrees"


class BirthWeight(BaseModel):
    value: float
    units: WeightUnits


class PlacentalWeight(BaseModel):
    value: float
    units: WeightUnits


class PregnancyLength(BaseModel):
    value: float
    units: TimeUnits


class DeliveryTimingField(BaseModel):
    value: DeliveryTiming


class DeliveryEaseField(BaseModel):
    value: DeliveryEase


class Pedigree(BaseModel):
    value: AnyUrl


class ChildOf(BaseModel):
    value: str


class SampleName(BaseModel):
    value: str


class Custom(BaseModel):
    sample_name: SampleName


class FAANGOrganismSample(SampleCoreMetadata):
    # required fields
    organism: Organism = Field(..., description="NCBI taxon ID of organism.")
    sex: Sex = Field(..., description="Animal sex, described using any child term of PATO_0000047.")

    # reccomended fields
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

    # optional fields
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





