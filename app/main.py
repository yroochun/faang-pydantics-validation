import json
from organisms_ruleset  import validate_faang_sample, validate_organism_array, validate_organisms_from_data


def main():
    # Example 1: Validate a single organism's core metadata
    print("=== Example 1: Single Organism Validation ===")
    single_organism_data = {
        "material": {
            "text": "organism",
            "term": "OBI:0100026",
            "ontology_name": "OBI"
        },
        "project": {
            "value": "FAANG"
        },
        "sample_description": {
            "value": "Adult female bovine liver sample"
        },
        "schema_version": "4.6.1"
    }

    try:
        validated_sample = validate_faang_sample(single_organism_data)
        print("✅ Single organism validation successful!")
        print(validated_sample.json(indent=2))
    except Exception as e:
        print(f"❌ Single organism validation failed: {e}")

    print("\n" + "=" * 60 + "\n")

    # Example 2: Validate organism array from JSON file
    print("=== Example 2: Organism Array Validation from File ===")

    # Replace 'sample1.json' with the path to your JSON file
    json_file_path = 'sample1.json'

    results = validate_organism_array(json_file_path)

    if results['success']:
        print("🎉 All organisms validated successfully!")
    else:
        if 'error' in results:
            print(f"❌ Validation failed: {results['error']}")
        else:
            print("⚠️  Some organisms failed validation. Check the failed_organisms list for details.")

            # Print details about failed validations
            if results['failed_organisms']:
                print("\nFailed Organisms:")
                for failed in results['failed_organisms']:
                    print(f"  - {failed['sample_name']}: {failed['error']}")

    print("\n" + "=" * 60 + "\n")

    # Example 3: Validate organism array from loaded data (most flexible)
    print("=== Example 3: Organism Array Validation from Loaded Data ===")

    try:
        # Load your JSON data
        with open('sample1.json', 'r') as f:
            data = json.load(f)

        # Extract and validate just the organism array
        if 'organism' in data:
            organism_results = validate_organisms_from_data(data['organism'])

            if organism_results['success']:
                print("🎉 All organisms from loaded data validated successfully!")
            else:
                print("⚠️  Some organisms failed validation.")

                # Show any failures
                if organism_results['failed_organisms']:
                    print("\nFailed Organisms:")
                    for failed in organism_results['failed_organisms']:
                        print(f"  - {failed['sample_name']}: {failed['error']}")
        else:
            print("❌ No organism array found in the JSON data")

    except FileNotFoundError:
        print("❌ sample1.json file not found")
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON format: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()

# class User(BaseModel):
#     name: str
#     age: int
#
#     class Config:
#         strict = True
#         frozen = True
#         extra = "forbid"

# use enum/literal to restrict options for columns
# model validation
# deserialise json object to know if it is valid or not