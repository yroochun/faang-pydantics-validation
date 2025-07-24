from pydantic import BaseModel, Field, validator, AnyUrl
from ..organism_validator_classes import OntologyValidator
from typing import List, Optional, Union, Literal
import re

from app.rulesets_pydantics.standard_ruleset import SampleCoreMetadata


class OrganModel(BaseModel):
    ontology_name: Literal["UBERON", "BTO"]
    text: str
    term: Union[str, Literal["restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_organ_model(cls, v, values, **kwargs):
        if v == "restricted access":
            return v

        ont = values.get('ontology_name')
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["UBERON:0001062", "BTO:0000042"]
        )
        if res.errors:
            raise ValueError(f"Organ model term invalid: {res.errors}")
        return v


class OrganPartModel(BaseModel):
    ontology_name: Literal["UBERON", "BTO"]
    text: str
    term: Union[str, Literal["restricted access"]]

    _ov = OntologyValidator(cache_enabled=True)

    @validator('term')
    def validate_organ_part_model(cls, v, values, **kwargs):
        if v == "restricted access":
            return v

        ont = values.get('ontology_name')
        res = cls._ov.validate_ontology_term(
            term=v,
            ontology_name=ont,
            allowed_classes=["UBERON:0001062", "BTO:0000042"]
        )
        if res.errors:
            raise ValueError(f"Organ part model term invalid: {res.errors}")
        return v


class FreezingDate(BaseModel):
    value: Union[str, Literal["restricted access"]]
    units: Literal["YYYY-MM-DD", "YYYY-MM", "YYYY", "restricted access"]

    @validator('value')
    def validate_freezing_date(cls, v, values):
        if v == "restricted access":
            return v

        pattern = r'^[12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])|[12]\d{3}-(0[1-9]|1[0-2])|[12]\d{3}$'

        if not re.match(pattern, v):
            raise ValueError(f"Invalid freezing date format: {v}. Must match YYYY-MM-DD, YYYY-MM, or YYYY pattern")

        return v


class FreezingMethod(BaseModel):
    value: Literal[
        "ambient temperature",
        "cut slide",
        "fresh",
        "frozen, -70 freezer",
        "frozen, -150 freezer",
        "frozen, liquid nitrogen",
        "frozen, vapor phase",
        "paraffin block",
        "RNAlater, frozen",
        "TRIzol, frozen"
    ]


class FreezingProtocol(BaseModel):
    value: Union[AnyUrl, Literal["restricted access"]]


class NumberOfFrozenCells(BaseModel):
    value: float
    units: Literal["organoids"] = "organoids"


class OrganoidPassage(BaseModel):
    value: float
    units: Literal["passages"] = "passages"


class OrganoidPassageProtocol(BaseModel):
    value: Union[AnyUrl, Literal["restricted access"]]


class OrganoidCultureAndPassageProtocol(BaseModel):
    value: Union[AnyUrl, Literal["restricted access"]]


class GrowthEnvironment(BaseModel):
    value: Literal["matrigel", "liquid suspension", "adherent"]


class TypeOfOrganoidCulture(BaseModel):
    value: Literal["2D", "3D"]


class OrganoidMorphology(BaseModel):
    value: str


class DerivedFrom(BaseModel):
    value: str


class FAANGOrganoidSample(SampleCoreMetadata):
    # required fields
    organ_model: OrganModel = Field(...,
                                    description="Organ for which this organoid is a model system e.g. 'heart' or 'liver'. High level organ term.")
    freezing_method: FreezingMethod = Field(...,
                                            description="Method of freezing of organoid. Temperatures are in celsius. 'Frozen, vapor phase' refers to storing samples above liquid nitrogen in the vapor.")
    organoid_passage: OrganoidPassage = Field(...,
                                              description="Number of passages. Passage 0 is the plating of cells to create the organoid")
    organoid_passage_protocol: OrganoidPassageProtocol = Field(...,
                                                               description="A link to the protocol for organoid passage.")
    type_of_organoid_culture: TypeOfOrganoidCulture = Field(...,
                                                            description="Whether the organoid culture two dimensional or three dimensional.")
    growth_environment: GrowthEnvironment = Field(...,
                                                  description="Growth environment in which the organoid is grown. e.g. 'matrigel', 'liquid suspension' or 'adherent'.")
    derived_from: DerivedFrom = Field(..., description="Sample name or BioSample ID for a specimen or organoid record.")

    # conditionally required based on freezing_method
    freezing_date: Optional[FreezingDate] = Field(None, description="Date that the organoid was frozen.")
    freezing_protocol: Optional[FreezingProtocol] = Field(None, description="A link to the protocol for freezing.")

    # optional fields
    organ_part_model: Optional[OrganPartModel] = Field(None,
                                                       description="Organ part for which this organoid is a model system e.g. 'bone marrow' or 'islet of Langerhans'. More specific part of organ.")
    number_of_frozen_cells: Optional[NumberOfFrozenCells] = Field(None,
                                                                  description="Number of organoids cells that were frozen.")
    organoid_culture_and_passage_protocol: Optional[OrganoidCultureAndPassageProtocol] = Field(None,
                                                                                               description="Protocol for the culture and passage of organoids, growth environment (matrigel or other); incubation temperature and oxygen level are expected in this protocol")
    organoid_morphology: Optional[OrganoidMorphology] = Field(None,
                                                              description="General description of the organoid morphology. e.g. 'Epithelial monolayer with budding crypt-like domains' or 'Optic cup structure'. Be consistent within your project if multiple similar samples.")

    @validator('freezing_date')
    def validate_freezing_date_required(cls, v, values):
        freezing_method = values.get('freezing_method')
        if freezing_method and freezing_method.value != 'fresh' and v is None:
            raise ValueError("freezing_date is required when freezing_method is not 'fresh'")
        return v

    @validator('freezing_protocol')
    def validate_freezing_protocol_required(cls, v, values):
        freezing_method = values.get('freezing_method')
        if freezing_method and freezing_method.value != 'fresh' and v is None:
            raise ValueError("freezing_protocol is required when freezing_method is not 'fresh'")
        return v

    class Config:
        extra = "forbid"
        validate_all = True
        validate_assignment = True