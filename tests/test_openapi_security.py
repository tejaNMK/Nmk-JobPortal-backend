from app.main import init_app


def test_nested_jwt_dependencies_are_marked_with_bearer_auth():
    app = init_app()

    schema = app.openapi()

    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter: Bearer <your-jwt-token>",
    }
    assert schema["paths"]["/candidate/applications"]["post"]["security"] == [
        {"bearerAuth": []}
    ]
    assert schema["paths"]["/candidate/applications"]["get"]["security"] == [
        {"bearerAuth": []}
    ]
    assert schema["paths"]["/candidate/applications/next-steps"]["get"]["security"] == [
        {"bearerAuth": []}
    ]
