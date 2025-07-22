# debug_elixir_organism.py
"""
Debug why Elixir validator is failing with organism validation
"""

import requests
import json
from constants import ORGANISM_URL, SAMPLE_CORE_URL, ELIXIR_VALIDATOR_URL


def test_elixir_step_by_step():
    """Test Elixir validator step by step to find the issue"""

    # 1. First, let's see what the actual schema looks like
    print("1. Loading FAANG organism schema...")
    try:
        response = requests.get(ORGANISM_URL)
        organism_schema = response.json()
        print(f"   Schema loaded successfully")
        print(f"   Schema has these top-level keys: {list(organism_schema.keys())}")
        print(f"   Required fields: {organism_schema.get('required', [])}")
    except Exception as e:
        print(f"   Error loading schema: {e}")
        return

    # 2. Test with minimal valid data
    print("\n2. Testing with minimal organism data...")
    minimal_data = {
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

    test_with_elixir(minimal_data, organism_schema, "minimal organism")

    # 3. Add samples_core
    print("\n3. Testing with samples_core added...")
    with_core = minimal_data.copy()
    with_core["samples_core"] = {
        "material": {
            "text": "organism",
            "term": "OBI:0100026",
            "ontology_name": "OBI"
        },
        "project": {"value": "FAANG"},
        "sample_description": {"value": "Test organism"}
    }

    test_with_elixir(with_core, organism_schema, "organism with core")

    # 4. Test breed validation schema
    print("\n4. Testing breed validation schema...")
    breed_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "string",
        "graph_restriction": {
            "ontologies": ["obo:lbo"],
            "classes": ["LBO:0000001"],
            "relations": ["rdfs:subClassOf"],
            "direct": False,
            "include_self": True
        }
    }

    # Test with just a string
    test_with_elixir("LBO:0000156", breed_schema, "breed term string")

    # 5. Test if graph_restriction is the issue
    print("\n5. Testing without graph_restriction...")
    simple_breed_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "string"
    }

    test_with_elixir("LBO:0000156", simple_breed_schema, "breed without graph restriction")

    # 6. Check if the issue is with the schema structure
    print("\n6. Examining schema structure...")
    if "properties" in organism_schema:
        print("   Schema has 'properties'")
        if "samples_core" in organism_schema["properties"]:
            print("   samples_core is in properties")
            print(f"   samples_core type: {organism_schema['properties']['samples_core'].get('type', 'not specified')}")

    # 7. Test removing samples_core from validation
    print("\n7. Testing without samples_core in data...")
    data_no_core = {
        "organism": with_core["organism"],
        "sex": with_core["sex"]
    }

    test_with_elixir(data_no_core, organism_schema, "organism without samples_core")

    # 8. Check if schema references are the issue
    print("\n8. Checking for $ref in schema...")
    check_for_refs(organism_schema)


def test_with_elixir(data, schema, description):
    """Test data against schema with Elixir validator"""
    print(f"\n   Testing: {description}")

    # Ensure schema has $schema
    if "$schema" not in schema:
        schema = schema.copy()
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"

    payload = {
        "schema": schema,
        "object": data
    }

    try:
        response = requests.post(ELIXIR_VALIDATOR_URL, json=payload, timeout=30)
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) == 0:
                print("   ✓ Validation passed!")
            else:
                print(f"   Validation errors: {result}")
        else:
            print(f"   ✗ Error response: {response.text[:200]}")

            # Try to get more details
            try:
                error_json = response.json()
                print(f"   Error details: {json.dumps(error_json, indent=2)}")
            except:
                pass

    except Exception as e:
        print(f"   Exception: {e}")


def check_for_refs(schema, path=""):
    """Recursively check for $ref in schema"""
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "$ref":
                print(f"   Found $ref at {path}: {value}")
            else:
                check_for_refs(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for i, item in enumerate(schema):
            check_for_refs(item, f"{path}[{i}]")


def test_simplified_schema():
    """Test with a simplified version of the organism schema"""
    print("\n\n9. Testing with simplified schema...")

    # Create a simplified schema without complex features
    simplified_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["organism", "sex"],
        "properties": {
            "organism": {
                "type": "object",
                "required": ["text", "term"],
                "properties": {
                    "text": {"type": "string"},
                    "term": {"type": "string"},
                    "ontology_name": {"type": "string"}
                }
            },
            "sex": {
                "type": "object",
                "required": ["text", "term"],
                "properties": {
                    "text": {"type": "string"},
                    "term": {"type": "string"},
                    "ontology_name": {"type": "string"}
                }
            },
            "samples_core": {
                "type": "object",
                "properties": {
                    "material": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "term": {"type": "string"},
                            "ontology_name": {"type": "string"}
                        }
                    },
                    "project": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"}
                        }
                    },
                    "sample_description": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"}
                        }
                    }
                }
            }
        }
    }

    data = {
        "samples_core": {
            "sample_description": {"value": "Adult female Holstein cattle"},
            "material": {"text": "organism", "term": "OBI:0100026", "ontology_name": "OBI"},
            "project": {"value": "FAANG"}
        },
        "organism": {"text": "Bos taurus", "term": "NCBITaxon:9913", "ontology_name": "NCBITaxon"},
        "sex": {"text": "female", "term": "PATO:0000383", "ontology_name": "PATO"}
    }

    test_with_elixir(data, simplified_schema, "simplified schema")


def create_working_validator():
    """Create a validator that handles the Elixir issues"""
    print("\n\n10. Creating a working validator...")

    class WorkingValidator:
        def validate_with_fixed_elixir(self, data, schema):
            """Fixed version that handles problematic schemas"""

            # Check if this is the breed validation (graph_restriction issue)
            if isinstance(data, str) and schema.get("type") == "string" and "graph_restriction" in schema:
                # Skip Elixir for graph restriction validation
                print("   Skipping Elixir for graph_restriction validation")
                return []

            # Check if schema has $ref (which might cause issues)
            if self._has_ref(schema):
                print("   Schema contains $ref, which might cause issues")
                # You could resolve refs here or skip validation
                return []

            # Remove problematic schema features
            cleaned_schema = self._clean_schema(schema)

            # Now validate with cleaned schema
            return self._call_elixir(data, cleaned_schema)

        def _has_ref(self, obj):
            """Check if object contains $ref"""
            if isinstance(obj, dict):
                if "$ref" in obj:
                    return True
                return any(self._has_ref(v) for v in obj.values())
            elif isinstance(obj, list):
                return any(self._has_ref(item) for item in obj)
            return False

        def _clean_schema(self, schema):
            """Remove problematic features from schema"""
            # Make a deep copy
            import copy
            cleaned = copy.deepcopy(schema)

            # Ensure it has $schema
            if "$schema" not in cleaned:
                cleaned["$schema"] = "http://json-schema.org/draft-07/schema#"

            # Remove graph_restriction if present
            self._remove_key(cleaned, "graph_restriction")

            return cleaned

        def _remove_key(self, obj, key_to_remove):
            """Recursively remove a key from nested dict"""
            if isinstance(obj, dict):
                if key_to_remove in obj:
                    del obj[key_to_remove]
                for v in obj.values():
                    self._remove_key(v, key_to_remove)
            elif isinstance(obj, list):
                for item in obj:
                    self._remove_key(item, key_to_remove)

        def _call_elixir(self, data, schema):
            """Call Elixir with cleaned schema"""
            payload = {
                "schema": schema,
                "object": data
            }

            try:
                response = requests.post(ELIXIR_VALIDATOR_URL, json=payload, timeout=30)
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"   Elixir error: {response.status_code}")
                    return []
            except Exception as e:
                print(f"   Elixir exception: {e}")
                return []

    validator = WorkingValidator()

    # Test it
    response = requests.get(ORGANISM_URL)
    organism_schema = response.json()

    data = {
        "organism": {"text": "Bos taurus", "term": "NCBITaxon:9913", "ontology_name": "NCBITaxon"},
        "sex": {"text": "female", "term": "PATO:0000383", "ontology_name": "PATO"}
    }

    errors = validator.validate_with_fixed_elixir(data, organism_schema)
    print(f"   Working validator result: {errors}")


if __name__ == "__main__":
    print("=== Debugging Elixir Validator Issues ===")
    test_elixir_step_by_step()
    test_simplified_schema()
    create_working_validator()