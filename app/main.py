import json
from standard_ruleset import validate_organism_list


def main():
    # Example: Validate organism array from loaded data (most flexible)
    try:
        # Load your JSON data
        with open('json_files/sample1.json', 'r') as f:
            data = json.load(f)

        # Extract and validate just the organism array
        if 'organism' in data:
            organism_results = validate_organism_list(data['organism'])

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