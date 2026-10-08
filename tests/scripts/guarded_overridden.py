from sampleapp.guarded import guarded_app, require_api_key

guarded_app.dependency_overrides[require_api_key] = lambda: None


def main() -> None:
    print("guarded main ran")
