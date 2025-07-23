import json


def main():
    try:
        # Load your JSON data
        with open('json_files/sample1.json', 'r') as f:
            data = json.load(f)

    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()

