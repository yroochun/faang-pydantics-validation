from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, List, Literal


class SampleDescription(BaseModel):
    value: Optional[str] = Field(None, description="A brief description of the sample including species name")


class Material(BaseModel):
    text: Literal[
        "organism",
        "specimen from organism",
        "cell specimen",
        "single cell specimen",
        "pool of specimens",
        "cell culture",
        "cell line",
        "organoid",
        "restricted access"
    ] = Field(..., description="The type of material being described")

    term: Literal[
        "OBI:0100026",  # organism
        "OBI:0001479",  # specimen from organism
        "OBI:0001468",  # cell specimen
        "OBI:0002127",  # single cell specimen
        "OBI:0302716",  # pool of specimens
        "OBI:0001876",  # cell culture
        "CLO:0000031",  # cell line
        "NCIT:C172259",  # organoid
        "restricted access"
    ] = Field(..., description="The ontology term for the material")

    ontology_name: Literal["OBI"] = "OBI"
    _comment: Optional[str] = Field(
        default="Covers organism, specimen from organism, cell specimen, pool of specimens, cell culture, cell line, organoid.",
        alias="_comment"
    )

    # check text and term consistency
    @validator('term')
    def validate_text_term_consistency(cls, v, values):
        if 'text' not in values:
            return v

        text_term_mapping = {
            "organism": "OBI:0100026",
            "specimen from organism": "OBI:0001479",
            "cell specimen": "OBI:0001468",
            "single cell specimen": "OBI:0002127",
            "pool of specimens": "OBI:0302716",
            "cell culture": "OBI:0001876",
            "cell line": "CLO:0000031",
            "organoid": "NCIT:C172259",
            "restricted access": "restricted access",
        }

        expected_term = text_term_mapping.get(values['text'])
        if expected_term and v != expected_term:
            raise ValueError(f"Term '{v}' does not match text '{values['text']}'. Expected term: '{expected_term}'")

        return v


class Project(BaseModel):
    value: Literal["FAANG"] = Field("FAANG", description="State that the project is 'FAANG'")


class SecondaryProject(BaseModel):
    value: Optional[Literal[
        "AQUA-FAANG",
        "BovReg",
        "GENE-SWitCH",
        "Bovine-FAANG",
        "EFFICACE",
        "GEroNIMO",
        "RUMIGEN",
        "Equine-FAANG",
        "Holoruminant",
        "USPIGFAANG"
    ]] = Field(None, description="Secondary project name")


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
    # required fields
    material: Material = Field(..., description="The type of material being described")
    project: Project = Field(..., description="State that the project is 'FAANG'")

    # optional fields
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
        description="Optional: BioSample ID for an equivalent sample record, created before the FAANG metadata "
                    "specification was available. This is optional and not intended for general use, "
                    "please contact the data coordination centre (faang-dcc@ebi.ac.uk) before using it."
    )
    secondary_project: Optional[List[SecondaryProject]] = Field(
        None,
        description="Optional: State the secondary project(s) that this data belongs to e.g. 'AQUA-FAANG', "
                    "'GENE-SWitCH' or 'BovReg'. Please use your official consortium shortened acronym if available. "
                    "If your secondary project is not in the list, please contact the faang-dcc helpdesk to have it "
                    "added. If your project uses the FAANG data portal project slices "
                    "(https://data.faang.org/projects) then this field is required to ensure that your data appears in "
                    "the data slice."
    )

    class Config:
        allow_population_by_field_name = True



